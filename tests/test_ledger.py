import asyncio
from uuid import uuid4

import pytest

from tokenops_guard.exceptions import (
    AuthorizationError,
    ConfigurationMismatchError,
    DuplicateCallError,
    RunHaltedError,
    SettlementConflictError,
)
from tokenops_guard.models import RunStatus, Usage

from .conftest import configured


async def reserve(ledger, settings, ctx, cost=400000, tokens=100):
    call = str(uuid4())
    ok = await ledger.reserve_budget(
        ctx, call, cost=cost, tokens=tokens, model=settings.model_routing.primary, settings=settings
    )
    return call, ok


async def test_isolated_runs(ledger, settings):
    first, second = await ledger.create_run(settings), await ledger.create_run(settings)
    await reserve(ledger, settings, first.context)
    assert (await ledger.get_run_status(first.context.run_id)).reserved == 400000
    assert (await ledger.get_run_status(second.context.run_id)).reserved == 0


async def test_atomic_five_reservations_one_dollar(ledger, settings):
    settings = configured(settings, budget__max_usd="1.00")
    ctx = (await ledger.create_run(settings)).context
    results = await asyncio.gather(
        *(reserve(ledger, settings, ctx.child(str(i))) for i in range(5))
    )
    assert sum(ok for _, ok in results) == 2
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent + s.reserved <= s.budget
    assert s.reserved == 800000 and s.active == s.calls == 2


async def test_idempotent_settle_releases_unused_reserve(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    call, ok = await reserve(ledger, settings, ctx)
    assert ok
    usage = Usage(input_tokens=10, output_tokens=20)
    await asyncio.gather(
        *(ledger.settle_budget(ctx.run_id, call, cost=100000, usage=usage) for _ in range(8))
    )
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent == 100000 and s.reserved == s.reserved_tokens == s.active == 0
    assert s.input_tokens == 10 and s.output_tokens == 20
    assert (await ledger.get_agent_spending(ctx.run_id, ctx.agent_id))["spent"] == 100000
    assert (await ledger.get_model_spending(ctx.run_id, "primary_model"))["spent"] == 100000
    with pytest.raises(SettlementConflictError):
        await ledger.settle_budget(ctx.run_id, call, cost=200000, usage=usage)


async def test_duplicate_reservation_never_increments(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    call, _ = await reserve(ledger, settings, ctx)
    with pytest.raises(DuplicateCallError):
        await ledger.reserve_budget(
            ctx, call, cost=400000, tokens=100, model="primary_model", settings=settings
        )
    assert (await ledger.get_run_status(ctx.run_id)).reserved == 400000


async def test_halt_is_sticky_and_authorized_resume(ledger, settings):
    handle = await ledger.create_run(settings)
    ctx = handle.context
    await ledger.halt(ctx.run_id, "operator_stop")
    with pytest.raises(RunHaltedError):
        await reserve(ledger, settings, ctx)
    with pytest.raises(AuthorizationError):
        await ledger.resume(ctx.run_id, admin_token="wrong", evidence="ticket-1")
    await ledger.resume(ctx.run_id, admin_token=handle.admin_token, evidence="ticket-1")
    assert (await ledger.get_run_status(ctx.run_id)).status == RunStatus.RUNNING


async def test_overrun_records_truth_then_halts(ledger, settings):
    settings = configured(settings, budget__max_usd="1")
    ctx = (await ledger.create_run(settings)).context
    call, _ = await reserve(ledger, settings, ctx, cost=400000)
    await ledger.settle_budget(
        ctx.run_id, call, cost=1200000, usage=Usage(input_tokens=10, output_tokens=20)
    )
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent == 1200000 and s.remaining == -200000
    assert s.status == RunStatus.HALTED and s.halt_reason == "estimate_overrun"


async def test_token_reservations_are_atomic(ledger, settings):
    settings = configured(settings, budget__max_tokens=250)
    ctx = (await ledger.create_run(settings)).context
    results = await asyncio.gather(
        *(reserve(ledger, settings, ctx, cost=10, tokens=100) for _ in range(5))
    )
    assert sum(ok for _, ok in results) == 2
    assert (await ledger.get_run_status(ctx.run_id)).reserved_tokens == 200


async def test_lease_expiry_keeps_money_and_requires_reconciliation(ledger, settings):
    settings = configured(settings, reliability__lease_s=0.12, reliability__heartbeat_s=0.03)
    handle = await ledger.create_run(settings)
    ctx = handle.context
    call, _ = await reserve(ledger, settings, ctx)
    await asyncio.sleep(0.18)
    assert await ledger.reconcile_expired(ctx.run_id) == 1
    assert await ledger.reconcile_expired(ctx.run_id) == 0
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved == 400000 and s.active == 0 and s.status == RunStatus.HALTED
    with pytest.raises(RunHaltedError):
        await ledger.resume(ctx.run_id, admin_token=handle.admin_token, evidence="ticket")
    with pytest.raises(AuthorizationError):
        await ledger.resolve_billing(
            ctx.run_id,
            call,
            admin_token="wrong",
            cost=0,
            usage=Usage(input_tokens=0, output_tokens=0),
            evidence="invoice",
        )
    await ledger.resolve_billing(
        ctx.run_id,
        call,
        admin_token=handle.admin_token,
        cost=50000,
        usage=Usage(input_tokens=10, output_tokens=10),
        evidence="invoice",
    )
    assert (await ledger.get_run_status(ctx.run_id)).status == RunStatus.HALTED
    await ledger.resume(ctx.run_id, admin_token=handle.admin_token, evidence="ticket")
    assert (await ledger.get_run_status(ctx.run_id)).reserved == 0


async def test_late_settlement_after_unknown_is_exactly_once(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    call, _ = await reserve(ledger, settings, ctx)
    await ledger.mark_unknown(ctx.run_id, call)
    usage = Usage(input_tokens=10, output_tokens=10)
    await ledger.settle_budget(ctx.run_id, call, cost=20000, usage=usage)
    await ledger.settle_budget(ctx.run_id, call, cost=20000, usage=usage)
    s = await ledger.get_run_status(ctx.run_id)
    assert s.active == s.reserved == 0 and s.spent == 20000 and s.status == RunStatus.HALTED


async def test_no_ttl_on_live_runs_and_terminal_archive(ledger, settings):
    handle = await ledger.create_run(settings)
    ctx = handle.context
    assert await ledger.redis.ttl(ledger.keys(ctx.run_id)[0]) == -1
    with pytest.raises(RunHaltedError):
        await ledger.expire_terminal_run(ctx.run_id, admin_token=handle.admin_token)
    await ledger.finish(ctx.run_id)
    await ledger.expire_terminal_run(ctx.run_id, admin_token=handle.admin_token, ttl_s=60)
    assert 0 < await ledger.redis.ttl(ledger.keys(ctx.run_id)[0]) <= 60
    with pytest.raises(RunHaltedError):
        await reserve(ledger, settings, ctx)


async def test_missing_run_fail_closed(ledger, settings):
    handle = await ledger.create_run(settings)
    await ledger.redis.delete(*ledger.keys(handle.context.run_id))
    with pytest.raises(RunHaltedError):
        await reserve(ledger, settings, handle.context)


async def test_worker_cannot_loosen_stored_policy(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    altered = configured(settings, policies__step_cap__max_calls=200)
    with pytest.raises(ConfigurationMismatchError):
        await reserve(ledger, altered, ctx)


async def test_invalid_money_rejected(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    for value in (-1, 0.5, True, 10**13):
        with pytest.raises(ValueError):
            await reserve(ledger, settings, ctx, cost=value)
