import asyncio
import contextlib
from time import monotonic
from uuid import uuid4

from .config import Settings
from .context import RunContext, current_run
from .exceptions import (
    BudgetStoreUnavailableError,
    ConcurrencyLimitError,
    GovernanceError,
    ProviderNotDispatchedError,
    RunHaltedError,
)
from .ledger.redis_ledger import RedisLedger
from .models import LLMResponse, RunSnapshot, Usage
from .observability import log_event
from .policies.engine import CallPlan, PolicyEngine
from .pricing import cost_microdollars
from .providers.base import LLMProvider


class GovernedLLMClient:
    def __init__(self, ledger: RedisLedger, settings: Settings, providers: dict[str, LLMProvider]):
        self.ledger = ledger
        self.settings = settings
        self.providers = providers
        self.policies = PolicyEngine(settings)
        self._cleanup_tasks: set[asyncio.Task] = set()

    def estimate_worst_case(self, model: str, inputs: int, outputs: int) -> int:
        return cost_microdollars(
            self.settings.models[model],
            Usage(input_tokens=inputs, output_tokens=outputs),
            worst_case=True,
        )

    async def reserve_budget(self, ctx: RunContext, call_id: str, plan: CallPlan) -> bool:
        return await self.ledger.reserve_budget(
            ctx,
            call_id,
            cost=plan.cost,
            tokens=plan.tokens,
            model=plan.model,
            settings=self.settings,
        )

    async def pre_call(
        self, ctx: RunContext, call_id: str, prompt: str, max_output_tokens: int
    ) -> CallPlan:
        deadline = monotonic() + self.settings.policies.concurrency_cap.queue_timeout_s
        while True:
            try:
                # Reconcile crashed workers first. Expiry holds money and halts the run.
                await self.ledger.reconcile_expired(ctx.run_id)
                await self.ledger.preflight(ctx.run_id, self.settings)
                raw = await self.ledger.raw_status(ctx.run_id)
                snapshot = RunSnapshot.model_validate(
                    {k: v for k, v in raw.items() if k in RunSnapshot.model_fields}
                )
                plan = self.policies.choose(snapshot, prompt, max_output_tokens, self.providers)
                if plan is None:
                    await self.ledger.halt_if_unchanged(
                        ctx.run_id, int(raw["revision"]), "pre_call_worst_case"
                    )
                elif await self.reserve_budget(ctx, call_id, plan):
                    return plan
            except ConcurrencyLimitError:
                if self.settings.policies.concurrency_cap.action == "REJECT":
                    raise
            if monotonic() >= deadline:
                raise ConcurrencyLimitError("Admission queue timed out; provider was not called")
            await asyncio.sleep(0.02)

    async def _heartbeat(self, ctx: RunContext, call_id: str):
        cfg = self.settings.reliability
        while True:
            await asyncio.sleep(cfg.heartbeat_s)
            state = await self.ledger.heartbeat(ctx.run_id, call_id, cfg.lease_s)
            if state != "RESERVED":
                raise RunHaltedError("Reservation no longer live")

    async def execute(
        self, ctx: RunContext, call_id: str, plan: CallPlan, prompt: str
    ) -> LLMResponse:
        price = self.settings.models[plan.model]
        worker = asyncio.create_task(
            self.providers[price.provider].complete(
                prompt=prompt,
                price=price,
                max_output_tokens=plan.max_output_tokens,
                call_id=call_id,
            )
        )
        heartbeat = asyncio.create_task(self._heartbeat(ctx, call_id))
        try:
            async with asyncio.timeout(self.settings.reliability.request_timeout_s):
                done, _ = await asyncio.wait(
                    {worker, heartbeat}, return_when=asyncio.FIRST_COMPLETED
                )
                if heartbeat in done:
                    heartbeat.result()  # Store failure cancels the provider and holds its reserve.
                return await worker
        finally:
            worker.cancel()
            heartbeat.cancel()
            await asyncio.gather(worker, heartbeat, return_exceptions=True)

    async def settle_budget(
        self, ctx: RunContext, call_id: str, plan: CallPlan, response: LLMResponse
    ) -> dict:
        price = self.settings.models[plan.model]
        if response.provider != price.provider or response.model != price.model_id:
            raise ValueError("Response pricing identity mismatch; reconcile billing")
        cost = cost_microdollars(price, response.usage)
        return await self.ledger.settle_budget(
            ctx.run_id, call_id, cost=cost, usage=response.usage, request_id=response.request_id
        )

    async def post_call(
        self, ctx: RunContext, call_id: str, plan: CallPlan, prompt: str, response: LLMResponse
    ):
        settlement = await self.settle_budget(ctx, call_id, plan, response)
        if self.settings.observability.enabled:
            snapshot = await self.ledger.get_run_status(ctx.run_id)
            log_event(
                {
                    "kind": "SETTLED",
                    "run_id": str(ctx.run_id),
                    "agent_id": ctx.agent_id,
                    "call_id": call_id,
                    "model": plan.model,
                    "provider": response.provider,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "estimated_cost": plan.cost,
                    "actual_cost": settlement["actual_cost"],
                    "reserved_cost": snapshot.reserved,
                    "total_run_cost": snapshot.spent,
                    "remaining_budget": snapshot.remaining,
                    "execution_time_ms": settlement["execution_time_ms"],
                    "halt_reason": snapshot.halt_reason,
                }
            )
        # A completed response may itself exhaust the budget. Return that final response.
        snapshot = await self.ledger.get_run_status(ctx.run_id)
        if snapshot.status in {"RUNNING", "STEERED"}:
            await self.ledger.record_progress(ctx, prompt, response.text)

    async def handle_failure(self, ctx: RunContext, call_id: str, exc: BaseException):
        async def cleanup():
            try:
                if isinstance(exc, ProviderNotDispatchedError):
                    await self.ledger.settle_budget(
                        ctx.run_id, call_id, cost=0, usage=Usage(input_tokens=0, output_tokens=0)
                    )
                else:
                    reason = (
                        "cancelled"
                        if isinstance(exc, asyncio.CancelledError)
                        else "timeout"
                        if isinstance(exc, TimeoutError)
                        else "request_failed"
                    )
                    await self.ledger.mark_unknown(ctx.run_id, call_id, reason)
            except GovernanceError:
                # If Redis is down, reserve survives. Lease reconciliation holds it on recovery.
                # If admission never happened, CALL_MISSING is also harmless.
                log_event(
                    {
                        "kind": "RECONCILIATION_REQUIRED",
                        "run_id": str(ctx.run_id),
                        "call_id": call_id,
                    }
                )

        task = asyncio.create_task(cleanup())
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=2)

    async def complete(
        self, prompt: str, *, max_output_tokens: int = 256, call_id: str | None = None
    ) -> LLMResponse:
        if not isinstance(prompt, str) or not 1 <= max_output_tokens <= 10**9:
            raise ValueError("Expected text and a positive output cap <= 10^9")
        ctx = current_run().step()
        call_id = call_id or str(uuid4())
        # Retry of a call_id never dispatches twice. Retry with a NEW id requires a new reservation.
        try:
            plan = await self.pre_call(ctx, call_id, prompt, max_output_tokens)
        except (asyncio.CancelledError, BudgetStoreUnavailableError) as exc:
            # An interrupted Redis reply may already have committed a reservation.
            await self.handle_failure(ctx, call_id, exc)
            raise
        try:
            response = await self.execute(ctx, call_id, plan, prompt)
            await self.post_call(ctx, call_id, plan, prompt, response)
            return response
        except (asyncio.CancelledError, Exception) as exc:
            await self.handle_failure(ctx, call_id, exc)
            raise

    async def aclose(self):
        if self._cleanup_tasks:
            await asyncio.gather(*list(self._cleanup_tasks), return_exceptions=True)
