import asyncio
import multiprocessing
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from tokenops_guard.config import Settings
from tokenops_guard.context import RunContext
from tokenops_guard.exceptions import RunHaltedError
from tokenops_guard.ledger.redis_ledger import RedisLedger
from tokenops_guard.models import RunStatus, Usage

from .conftest import configured


def process_worker(url, prefix, ctx_json, settings_json, pipe, operation, gate=None):
    """Separate OS process, independent event loop, connection and context."""

    async def run():
        redis = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2, socket_timeout=3
        )
        ledger = RedisLedger(redis, prefix=prefix)
        ctx, settings = (
            RunContext.model_validate_json(ctx_json),
            Settings.model_validate_json(settings_json),
        )
        call = str(uuid4())
        try:
            if gate is not None:
                await asyncio.to_thread(gate.wait, 10)
            if operation == "halt_check":
                try:
                    await ledger.preflight(ctx.run_id, settings)
                    pipe.send("allowed")
                except RunHaltedError:
                    pipe.send("halted")
            else:
                ok = await ledger.reserve_budget(
                    ctx, call, cost=400000, tokens=100, model="primary_model", settings=settings
                )
                pipe.send({"ok": ok, "call_id": call})
                if operation == "crash":
                    pipe.close()
                    os._exit(23)
        except Exception as exc:
            pipe.send({"error": type(exc).__name__})
        finally:
            await redis.aclose()
            pipe.close()

    asyncio.run(run())


async def gather_processes(ledger, settings, ctx, operations, *, simultaneous=False):
    mp = multiprocessing.get_context("spawn")
    gate = mp.Event() if simultaneous else None
    url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    children, readers = [], []
    try:
        for operation in operations:
            reader, writer = mp.Pipe(duplex=False)
            process = mp.Process(
                target=process_worker,
                args=(
                    url,
                    ledger.prefix,
                    ctx.model_dump_json(),
                    settings.model_dump_json(),
                    writer,
                    operation,
                    gate,
                ),
            )
            process.start()
            writer.close()
            children.append(process)
            readers.append(reader)
        if gate is not None:
            gate.set()
        results = []
        for reader in readers:
            if not await asyncio.to_thread(reader.poll, 30):
                pytest.fail("Worker did not return within 30 seconds")
            results.append(reader.recv())
        for process in children:
            await asyncio.to_thread(process.join, 10)
            assert process.exitcode in {0, 23}
        return results
    finally:
        for reader in readers:
            reader.close()
        for process in children:
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 5)


async def test_five_independent_processes_share_one_dollar(ledger, settings):
    settings = configured(settings, budget__max_usd="1")
    ctx = (await ledger.create_run(settings)).context
    results = await gather_processes(ledger, settings, ctx, ["reserve"] * 5, simultaneous=True)
    assert not any("error" in r for r in results), results
    assert sum(r["ok"] for r in results) == 2
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent + s.reserved == 800000 <= s.budget
    assert s.calls == s.active == 2


async def test_crashed_process_holds_reserve_until_authorized_resolution(ledger, settings):
    settings = configured(settings, reliability__lease_s=0.15, reliability__heartbeat_s=0.03)
    handle = await ledger.create_run(settings)
    ctx = handle.context
    result = (await gather_processes(ledger, settings, ctx, ["crash"]))[0]
    assert result["ok"]
    await asyncio.sleep(0.2)
    await ledger.reconcile_expired(ctx.run_id)
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved == 400000 and s.status == RunStatus.HALTED
    await ledger.resolve_billing(
        ctx.run_id,
        result["call_id"],
        admin_token=handle.admin_token,
        cost=200000,
        usage=Usage(input_tokens=50, output_tokens=50),
        evidence="provider-invoice-verified",
    )
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent == 200000 and s.reserved == s.active == 0
    assert s.status == RunStatus.HALTED


async def test_halt_persists_between_processes(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    await ledger.halt(ctx.run_id, "operator")
    results = await gather_processes(ledger, settings, ctx, ["halt_check"] * 2)
    assert results == ["halted", "halted"]


async def test_parallel_settlements_and_reservations_preserve_invariant(ledger, settings):
    settings = configured(
        settings,
        budget__max_usd="1",
        policies__concurrency_cap__enabled=False,
        policies__cost_guard__enabled=False,
    )
    ctx = (await ledger.create_run(settings)).context

    async def request(i):
        call = str(uuid4())
        ok = await ledger.reserve_budget(
            ctx.child(str(i)),
            call,
            cost=200000,
            tokens=100,
            model="primary_model",
            settings=settings,
        )
        if ok:
            await asyncio.sleep(0.01)
            await ledger.settle_budget(
                ctx.run_id, call, cost=100000, usage=Usage(input_tokens=20, output_tokens=20)
            )
        s = await ledger.get_run_status(ctx.run_id)
        assert s.spent + s.reserved <= s.budget
        assert s.reserved >= 0 and s.active >= 0
        return ok

    assert sum(await asyncio.gather(*(request(i) for i in range(20)))) >= 5
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved == s.active == 0
