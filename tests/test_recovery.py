import asyncio
from uuid import uuid4

import pytest

from tokenops_guard.config import ModelPrice
from tokenops_guard.context import bind_run
from tokenops_guard.exceptions import BudgetStoreUnavailableError, ConcurrencyLimitError
from tokenops_guard.models import RunStatus, Usage
from tokenops_guard.pricing import cost_microdollars
from tokenops_guard.providers import FakeProvider
from tokenops_guard.wrapper import GovernedLLMClient

from .conftest import configured


def test_cache_categories_and_worst_case_are_separate(settings):
    price = ModelPrice.model_validate(
        {
            **settings.models["primary_model"].model_dump(),
            "input_usd_per_million": "2",
            "output_usd_per_million": "10",
            "input_billing_multiplier": "1.25",
            "cached_input_usd_per_million": "0.1",
            "cache_write_usd_per_million": "2.5",
        }
    )
    usage = Usage(
        input_tokens=1000, output_tokens=100, cached_input_tokens=400, cache_write_input_tokens=200
    )
    assert cost_microdollars(price, usage) == 2340  # 800+40+500+1000
    assert cost_microdollars(price, usage, worst_case=True) == 3500


async def test_cancelled_redis_ack_does_not_release_committed_reservation(
    ledger, settings, monkeypatch
):
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    original = client.reserve_budget

    async def interrupted(*args):
        assert await original(*args)
        raise asyncio.CancelledError()

    monkeypatch.setattr(client, "reserve_budget", interrupted)
    with bind_run(ctx), pytest.raises(asyncio.CancelledError):
        await client.complete("interrupted redis acknowledgement")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved > 0 and s.status == RunStatus.HALTED and not fake.calls


async def test_heartbeat_store_failure_halts_and_holds(ledger, settings, monkeypatch):
    settings = configured(settings, reliability__lease_s=0.2, reliability__heartbeat_s=0.04)
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=1)

    async def unavailable(*args):
        raise BudgetStoreUnavailableError("simulated heartbeat transport failure")

    monkeypatch.setattr(ledger, "heartbeat", unavailable)
    with bind_run(ctx), pytest.raises(BudgetStoreUnavailableError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("in flight")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved > 0 and s.active == 0 and s.status == RunStatus.HALTED


async def test_settlement_transport_failure_preserves_reserve(ledger, settings, monkeypatch):
    ctx = (await ledger.create_run(settings)).context
    client = GovernedLLMClient(ledger, settings, {"fake": FakeProvider()})
    original = ledger._op

    async def fail_settle(run_id, operation, **kwargs):
        if operation == "settle":
            raise BudgetStoreUnavailableError("settlement transport failed")
        return await original(run_id, operation, **kwargs)

    monkeypatch.setattr(ledger, "_op", fail_settle)
    with bind_run(ctx), pytest.raises(BudgetStoreUnavailableError):
        await client.complete("answer arrived but settlement is unavailable")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent == 0 and s.reserved > 0 and s.status == RunStatus.HALTED


async def test_queue_timeout_does_not_touch_other_reservation(ledger, settings):
    settings = configured(
        settings,
        policies__concurrency_cap__max_parallel_calls=1,
        policies__concurrency_cap__action="QUEUE",
        policies__concurrency_cap__queue_timeout_s=0.05,
    )
    ctx = (await ledger.create_run(settings)).context
    call = str(uuid4())
    assert await ledger.reserve_budget(
        ctx, call, cost=10000, tokens=100, model="primary_model", settings=settings
    )
    fake = FakeProvider()
    with bind_run(ctx), pytest.raises(ConcurrencyLimitError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("queued")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.status == RunStatus.RUNNING and s.reserved == 10000 and s.active == 1
    assert not fake.calls
