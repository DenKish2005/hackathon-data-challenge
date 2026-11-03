import pytest
from pydantic import ValidationError

from tokenops_guard.config import ModelPrice
from tokenops_guard.context import bind_run
from tokenops_guard.exceptions import BudgetExceededError, RunHaltedError
from tokenops_guard.models import RunStatus, Usage
from tokenops_guard.pricing import cost_microdollars
from tokenops_guard.providers import FakeProvider
from tokenops_guard.wrapper import GovernedLLMClient

from .conftest import configured


def test_decimal_cost_rounds_up(settings):
    price = ModelPrice.model_validate(
        {
            **settings.models["primary_model"].model_dump(),
            "input_usd_per_million": "0.1",
            "output_usd_per_million": "0.5",
        }
    )
    assert cost_microdollars(price, Usage(input_tokens=1, output_tokens=1)) == 1
    assert cost_microdollars(price, Usage(input_tokens=3, output_tokens=7)) == 4
    assert cost_microdollars(price, Usage(input_tokens=1000000, output_tokens=1000000)) == 600000


async def test_steer_at_eighty_percent_switches_once(ledger, settings):
    settings = configured(settings, budget__max_usd="1")
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    with bind_run(ctx):
        for i in range(4):
            await client.complete(f"step-{i}", max_output_tokens=100)
        s = await ledger.get_run_status(ctx.run_id)
        assert s.spent == 800000 and s.status == RunStatus.STEERED
        await client.complete("economy", max_output_tokens=256)
        await client.complete("economy2", max_output_tokens=256)
    assert [c["model"] for c in fake.calls[:4]] == ["fake-primary"] * 4
    assert all(c["model"] == "fake-economy" for c in fake.calls[4:])
    assert fake.calls[4]["max_output_tokens"] == 128
    assert len([e for e in await ledger.get_run_events(ctx.run_id) if e["kind"] == "STEER"]) == 1


async def test_pre_call_shrinks_then_uses_fallback(ledger, settings):
    settings = configured(settings, budget__max_usd="0.105")
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    with bind_run(ctx):
        client = GovernedLLMClient(ledger, settings, {"fake": fake})
        await client.complete("small", max_output_tokens=100)
    assert fake.calls[0]["max_output_tokens"] == 5
    assert (await ledger.get_run_status(ctx.run_id)).spent == 105000

    cheaper = configured(settings, budget__max_usd="0.05")
    other = (await ledger.create_run(cheaper)).context
    with bind_run(other):
        await GovernedLLMClient(ledger, cheaper, {"fake": fake}).complete(
            "fallback", max_output_tokens=100
        )
    assert fake.calls[-1]["model"] == "fake-economy"


async def test_halt_before_provider_if_nothing_fits(ledger, settings):
    settings = configured(settings, budget__max_usd="0.000001")
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    with bind_run(ctx), pytest.raises(BudgetExceededError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("no budget")
    assert len(fake.calls) == 0
    assert (await ledger.get_run_status(ctx.run_id)).status == RunStatus.HALTED


async def test_step_cap_stops_loop(ledger, settings):
    settings = configured(settings, policies__step_cap__max_steps=2)
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    with bind_run(ctx):
        await client.complete("one")
        await client.complete("two")
        with pytest.raises(RunHaltedError):
            await client.complete("three")
    assert len(fake.calls) == 2
    assert (await ledger.get_run_status(ctx.run_id)).halt_reason == "step_cap"


@pytest.mark.parametrize("sequence", [["A"] * 4, ["A", "B"] * 4, ["A", "B", "C"] * 4])
async def test_repeating_sequences_halt(ledger, settings, sequence):
    ctx = (await ledger.create_run(settings)).context
    with pytest.raises(RunHaltedError):
        for action in sequence:
            await ledger.record_step(ctx)
            await ledger.record_progress(ctx, action, "same-result")
    assert (await ledger.get_run_status(ctx.run_id)).halt_reason == "progress_guard"
    assert any(e["kind"] == "PROGRESS_WARNING" for e in await ledger.get_run_events(ctx.run_id))


def test_validation(settings):
    for changes in (
        {"reliability__fail_closed": False},
        {"budget__max_usd": "0.0000001"},
        {"reliability__heartbeat_s": 60},
        {"model_routing__primary": "unknown"},
        {"policies__cost_guard__threshold": "1.2"},
        {"models__economy_model__output_usd_per_million": "2000"},
    ):
        with pytest.raises(ValidationError):
            configured(settings, **changes)
