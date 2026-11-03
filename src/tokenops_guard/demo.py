"""Free, deterministic scenarios A-E. Run with tokenops-demo --scenario all."""

import argparse
import asyncio
import multiprocessing
from decimal import Decimal
from uuid import uuid4

from redis.asyncio import Redis

from .config import Settings, load_settings
from .context import RunContext, bind_run
from .exceptions import RunHaltedError
from .ledger.redis_ledger import RedisLedger
from .observability import console_summary
from .pricing import cost_microdollars
from .providers import FakeProvider
from .wrapper import GovernedLLMClient


def with_budget(settings: Settings, usd: str) -> Settings:
    data = settings.model_dump(mode="json")
    data["budget"]["max_usd"] = usd
    return Settings.model_validate(data)


class ResearchAgent:
    name = "ResearchAgent"

    async def run(self, ctx, client):
        # A tiny local RAG/tool step. Tool-only loops also consume the global step cap.
        await client.ledger.record_step(ctx)
        facts = "Redis Lua scripts execute atomically; reservations prevent concurrent overspend."
        await client.ledger.record_progress(ctx, "retrieve", facts)
        return await client.complete(
            "Research shared budgets using: " + facts, max_output_tokens=100
        )


class AnalysisAgent:
    name = "AnalysisAgent"

    async def run(self, ctx, client, research):
        return await client.complete("Analyze evidence: " + research.text, max_output_tokens=100)


class SummaryAgent:
    name = "SummaryAgent"

    async def run(self, ctx, client, analysis):
        return await client.complete("Summarize findings: " + analysis.text, max_output_tokens=100)


async def single_process_scenario(scenario: str, ledger: RedisLedger, settings: Settings):
    if scenario == "B":
        settings = with_budget(settings, "1")
    elif scenario == "C":
        settings = with_budget(settings, "0.000001")
    handle = await ledger.create_run(settings)
    ctx = handle.context
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    print(f"\nScenario {scenario}")
    try:
        if scenario == "A":
            research_agent, analysis_agent, summary_agent = (
                ResearchAgent(),
                AnalysisAgent(),
                SummaryAgent(),
            )
            with bind_run(ctx.child(research_agent.name)) as child:
                research = await research_agent.run(child, client)
            with bind_run(ctx.child(analysis_agent.name)) as child:
                analysis = await analysis_agent.run(child, client, research)
            with bind_run(ctx.child(summary_agent.name)) as child:
                result = await summary_agent.run(child, client, analysis)
            print("Three agents, one run_id. Final response:", result.text)
            await ledger.finish(ctx.run_id)
        elif scenario == "B":
            names = ["ResearchAgent", "AnalysisAgent", "SummaryAgent"]
            for i in range(6):
                with bind_run(ctx.child(names[i % 3])):
                    await client.complete(f"Distinct work item {i}", max_output_tokens=100)
                print(f"  call {i + 1}: {fake.calls[-1]['model']}")
            assert fake.calls[4]["model"] == "fake-economy"
            await ledger.finish(ctx.run_id)
        elif scenario == "C":
            with bind_run(ctx.child("SummaryAgent")):
                await client.complete("Cannot afford even one token")
        elif scenario == "D":
            with bind_run(ctx.child("ResearchAgent")):
                while True:
                    await client.complete("Repeat identical action", max_output_tokens=100)
    except RunHaltedError:
        print("Run halted by the shared policy; later calls will be refused.")
    finally:
        await client.aclose()
    snapshot = await ledger.get_run_status(ctx.run_id)
    print(console_summary(snapshot))
    print("Provider dispatches:", len(fake.calls))
    if scenario == "C":
        assert not fake.calls and snapshot.status == "HALTED"
    if scenario == "D":
        assert snapshot.halt_reason == "progress_guard" and len(fake.calls) == 4
    for event in await ledger.get_run_events(ctx.run_id):
        if event["kind"] in {"STEER", "HALT", "PROGRESS_WARNING"}:
            print("  event:", event["kind"], event.get("policy_triggered", ""))


def _concurrent_worker(url, prefix, ctx_json, settings_json, writer, dispatch_gate):
    async def work():
        redis = Redis.from_url(url, decode_responses=True, socket_timeout=5)
        ledger = RedisLedger(redis, prefix=prefix)
        ctx = RunContext.model_validate_json(ctx_json)
        settings = Settings.model_validate_json(settings_json)
        call_id = str(uuid4())
        try:
            admitted = await ledger.reserve_budget(
                ctx, call_id, cost=400000, tokens=400, model="primary_model", settings=settings
            )
            writer.send(admitted)
            if admitted:
                # Hold all reservations until the coordinator has observed the invariant.
                if not await asyncio.to_thread(dispatch_gate.wait, 30):
                    raise TimeoutError("Coordinator did not release workers")
                provider = FakeProvider(input_tokens=200, output_tokens=200)
                price = settings.models["primary_model"]
                result = await provider.complete(
                    prompt="concurrent work", price=price, max_output_tokens=200, call_id=call_id
                )
                await ledger.settle_budget(
                    ctx.run_id,
                    call_id,
                    cost=cost_microdollars(price, result.usage),
                    usage=result.usage,
                )
        finally:
            writer.close()
            await redis.aclose()

    asyncio.run(work())


async def concurrent_scenario(ledger: RedisLedger, settings: Settings):
    settings = with_budget(settings, "1")
    ctx = (await ledger.create_run(settings)).context
    mp = multiprocessing.get_context("spawn")
    gate = mp.Event()
    workers, readers = [], []
    print("\nScenario E: five independent processes reserve $0.40 against ONE $1.00 budget")
    try:
        for i in range(5):
            reader, writer = mp.Pipe(duplex=False)
            proc = mp.Process(
                target=_concurrent_worker,
                args=(
                    settings.redis_url,
                    ledger.prefix,
                    ctx.child(f"worker-{i}").model_dump_json(),
                    settings.model_dump_json(),
                    writer,
                    gate,
                ),
            )
            proc.start()
            writer.close()
            readers.append(reader)
            workers.append(proc)
        admitted = []
        for reader in readers:
            if not await asyncio.to_thread(reader.poll, 30):
                raise TimeoutError("Worker response missing")
            admitted.append(reader.recv())
        snapshot = await ledger.get_run_status(ctx.run_id)
        print("Admitted:", sum(admitted), "of 5; reserved:", Decimal(snapshot.reserved) / 1000000)
        assert sum(admitted) == 2
        assert snapshot.spent + snapshot.reserved <= snapshot.budget
        gate.set()
        for proc in workers:
            await asyncio.to_thread(proc.join, 30)
            if proc.exitcode != 0:
                raise RuntimeError("Worker failed; reconcile its lease before resuming")
        await ledger.finish(ctx.run_id)
        print(console_summary(await ledger.get_run_status(ctx.run_id)))
    finally:
        gate.set()
        for reader in readers:
            reader.close()
        for proc in workers:
            if proc.is_alive():
                proc.terminate()
                await asyncio.to_thread(proc.join, 5)


async def run_demo(scenario="all"):
    settings = load_settings()
    redis = Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=5
    )
    ledger = RedisLedger(redis)
    try:
        for name in "ABCDE" if scenario == "all" else scenario:
            if name == "E":
                await concurrent_scenario(ledger, settings)
            else:
                await single_process_scenario(name, ledger, settings)
    finally:
        await redis.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["all", "A", "B", "C", "D", "E"], default="all")
    args = parser.parse_args()
    asyncio.run(run_demo(args.scenario))


if __name__ == "__main__":
    main()
