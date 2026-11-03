import hashlib
import json
import secrets
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from importlib.resources import files
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..config import Settings
from ..context import RunContext
from ..exceptions import (
    AuthorizationError,
    BudgetExceededError,
    BudgetStoreUnavailableError,
    ConcurrencyLimitError,
    ConfigurationMismatchError,
    DuplicateCallError,
    GovernanceError,
    RunHaltedError,
    SettlementConflictError,
)
from ..models import MAX_MONEY, MAX_TOKENS, RunSnapshot, RunStatus, Usage


@dataclass(frozen=True)
class RunHandle:
    context: RunContext
    admin_token: str  # Server/operator capability; never send this to an agent.


class RedisLedger:
    def __init__(self, redis: Redis, *, prefix: str = "tokenops"):
        if not prefix or any(c in prefix for c in "{}"):
            raise ValueError("Invalid ledger namespace")
        self.redis = redis
        self.prefix = prefix
        self.script = (
            files("tokenops_guard.ledger")
            .joinpath("scripts/ledger.lua")
            .read_text(encoding="utf-8")
        )

    def keys(self, run_id: UUID | str) -> list[str]:
        base = self.prefix + ":{" + str(UUID(str(run_id))) + "}:"
        return [base + suffix for suffix in ("run", "calls", "events", "leases", "progress")]

    async def _read(self, method, *args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except (RedisError, OSError) as exc:
            raise BudgetStoreUnavailableError("Redis unavailable; paid calls are blocked") from exc

    async def _op(self, run_id, op: str, **args) -> dict:
        args["run_id"] = str(run_id)
        keys = self.keys(run_id)
        raw = await self._read(
            self.redis.eval,
            self.script,
            len(keys),
            *keys,
            op,
            json.dumps(args, separators=(",", ":")),
        )
        result = json.loads(raw)
        code, data = result["code"], result["data"]
        errors = {
            "MISSING": RunHaltedError,
            "HALTED": RunHaltedError,
            "BUDGET": BudgetExceededError,
            "CONCURRENCY": ConcurrencyLimitError,
            "CONFIG": ConfigurationMismatchError,
            "DUPLICATE": DuplicateCallError,
            "CONFLICT": SettlementConflictError,
            "AUTH": AuthorizationError,
            "UNRESOLVED": RunHaltedError,
            "CALL_MISSING": GovernanceError,
            "EXISTS": GovernanceError,
        }
        if code in errors:
            # Error messages never include provider exception strings or prompts.
            raise errors[code](f"{code}: {data if isinstance(data, str) else ''}")
        if code not in {"OK", "RETRY"}:
            raise GovernanceError(f"Unexpected ledger response: {code}")
        return result

    async def create_run(
        self,
        settings: Settings,
        *,
        agent_id: str = "coordinator",
        parent_run_id: UUID | None = None,
    ) -> RunHandle:
        if parent_run_id is not None:
            raise ValueError("Use get_context(parent_run_id).child() to share a parent's budget")
        ctx = RunContext(
            agent_id=agent_id,
            budget_usd=settings.budget.max_usd,
            max_tokens=settings.budget.max_tokens,
        )
        admin = secrets.token_urlsafe(32)
        await self._op(
            ctx.run_id,
            "create",
            budget=int(ctx.budget_usd * 1000000),
            max_tokens=ctx.max_tokens,
            context=ctx.model_dump_json(),
            settings=settings.model_dump_json(),
            fingerprint=settings.fingerprint(),
            admin_hash=self._admin_hash(admin),
            steer_at=self._steer_at(int(ctx.budget_usd * 1000000), settings),
        )
        return RunHandle(ctx, admin)

    @staticmethod
    def _admin_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _steer_at(budget: int, settings: Settings) -> int:
        return int(
            (Decimal(budget) * settings.policies.cost_guard.threshold).to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    async def raw_status(self, run_id: UUID | str) -> dict:
        raw = await self._read(self.redis.hgetall, self.keys(run_id)[0])
        if not raw:
            raise RunHaltedError("Missing/expired run; never recreated automatically")
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    async def get_run_status(self, run_id: UUID | str) -> RunSnapshot:
        raw = await self.raw_status(run_id)
        return RunSnapshot.model_validate(
            {k: v for k, v in raw.items() if k in RunSnapshot.model_fields}
        )

    async def get_context(self, run_id: UUID | str, agent_id: str) -> RunContext:
        raw = await self.raw_status(run_id)
        ctx = RunContext.model_validate_json(raw["context"])
        return RunContext.model_validate(
            {
                **ctx.model_dump(),
                "budget_usd": Decimal(raw["budget"]) / 1000000,
                "max_tokens": int(raw["max_tokens"]),
                "status": raw["status"],
            }
        ).child(agent_id)

    async def get_run_spending(self, run_id: UUID | str) -> dict:
        s = await self.get_run_status(run_id)
        return {
            "spent": s.spent,
            "reserved": s.reserved,
            "remaining": s.remaining,
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
        }

    async def get_run_events(
        self, run_id: UUID | str, *, start: int = 0, limit: int = 1000
    ) -> list[dict]:
        if start < 0 or not 1 <= limit <= 10000:
            raise ValueError("Invalid event page")
        rows = await self._read(self.redis.lrange, self.keys(run_id)[2], start, start + limit - 1)
        return [json.loads(row) for row in rows]

    async def get_agent_spending(self, run_id, agent_id: str) -> dict:
        raw = await self._read(self.redis.hget, self.keys(run_id)[0], "agent:" + agent_id)
        return (
            json.loads(raw)
            if raw
            else {"spent": 0, "input_tokens": 0, "output_tokens": 0, "calls": 0}
        )

    async def get_model_spending(self, run_id, model: str) -> dict:
        raw = await self._read(self.redis.hget, self.keys(run_id)[0], "model:" + model)
        return (
            json.loads(raw)
            if raw
            else {"spent": 0, "input_tokens": 0, "output_tokens": 0, "calls": 0}
        )

    async def get_call(self, run_id, call_id: str) -> dict:
        raw = await self._read(self.redis.hget, self.keys(run_id)[1], str(UUID(call_id)))
        if raw is None:
            raise GovernanceError("Unknown call_id")
        return json.loads(raw)

    async def preflight(self, run_id, settings: Settings):
        await self._op(run_id, "preflight", fingerprint=settings.fingerprint())

    async def reserve_budget(
        self,
        ctx: RunContext,
        call_id: str,
        *,
        cost: int,
        tokens: int,
        model: str,
        settings: Settings,
    ) -> bool:
        self._bounds(cost, tokens)
        if model not in settings.models:
            raise ValueError("Unknown model")
        result = await self._op(
            ctx.run_id,
            "reserve",
            call_id=str(UUID(call_id)),
            cost=cost,
            tokens=tokens,
            model=model,
            provider=settings.models[model].provider,
            agent_id=ctx.agent_id,
            step_id=ctx.step_id,
            trace_id=str(ctx.trace_id),
            fingerprint=settings.fingerprint(),
            lease_ms=int(settings.reliability.lease_s * 1000),
        )
        return result["code"] == "OK"

    @staticmethod
    def _bounds(cost, tokens):
        if type(cost) is not int or type(tokens) is not int:
            raise ValueError("Money and tokens must be integers")
        if not 0 <= cost <= MAX_MONEY or not 0 <= tokens <= MAX_TOKENS:
            raise ValueError("Money or token count outside supported range")

    async def settle_budget(
        self, run_id, call_id: str, *, cost: int, usage: Usage, request_id: str | None = None
    ) -> dict:
        self._bounds(cost, usage.input_tokens + usage.output_tokens)
        return (
            await self._op(
                run_id,
                "settle",
                call_id=str(UUID(call_id)),
                cost=cost,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_write_input_tokens=usage.cache_write_input_tokens,
                request_id=request_id,
                evidence=None,
            )
        )["data"]

    async def mark_unknown(self, run_id, call_id: str, reason: str = "provider_failure"):
        await self._op(run_id, "unknown", call_id=str(UUID(call_id)), reason=reason)

    async def heartbeat(self, run_id, call_id: str, lease_s: float):
        return (
            await self._op(
                run_id, "heartbeat", call_id=str(UUID(call_id)), lease_ms=int(lease_s * 1000)
            )
        )["data"]

    async def reconcile_expired(self, run_id) -> int:
        return (await self._op(run_id, "reconcile"))["data"]

    async def resolve_billing(
        self, run_id, call_id: str, *, admin_token: str, cost: int, usage: Usage, evidence: str
    ):
        self._bounds(cost, usage.input_tokens + usage.output_tokens)
        if not evidence or len(evidence) > 200:
            raise ValueError("Provide a non-secret billing evidence reference (<=200 chars)")
        await self._op(
            run_id,
            "resolve",
            call_id=str(UUID(call_id)),
            cost=cost,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_input_tokens=usage.cache_write_input_tokens,
            admin_hash=self._admin_hash(admin_token),
            evidence=evidence,
            request_id=None,
        )

    async def halt(self, run_id, reason: str):
        await self._op(run_id, "halt", reason=reason)

    async def halt_if_unchanged(self, run_id, revision: int, reason: str) -> bool:
        return (await self._op(run_id, "halt_if_unchanged", revision=revision, reason=reason))[
            "code"
        ] == "OK"

    async def resume(
        self,
        run_id,
        *,
        admin_token: str,
        budget: int | None = None,
        max_tokens: int | None = None,
        evidence: str,
    ):
        raw = await self.raw_status(run_id)
        budget = budget if budget is not None else int(raw["budget"])
        max_tokens = max_tokens if max_tokens is not None else int(raw["max_tokens"])
        self._bounds(budget, max_tokens)
        if not evidence or len(evidence) > 200:
            raise ValueError("Operator evidence reference required (<=200 chars)")
        await self._op(
            run_id,
            "resume",
            admin_hash=self._admin_hash(admin_token),
            budget=budget,
            max_tokens=max_tokens,
            evidence=evidence,
            steer_at=self._steer_at(budget, Settings.model_validate_json(raw["settings"])),
        )

    async def record_progress(self, ctx: RunContext, action: str, result: str):
        # Hash contents; no prompts, tool results or customer data in audit storage.
        fingerprint = hashlib.sha256(json.dumps([action, result]).encode()).hexdigest()
        await self._op(ctx.run_id, "progress", agent_id=ctx.agent_id, fingerprint=fingerprint)

    async def record_step(self, ctx: RunContext):
        await self._op(ctx.run_id, "step", agent_id=ctx.agent_id, step_id=ctx.step_id)

    async def finish(self, run_id, status: RunStatus = RunStatus.COMPLETED):
        if status not in {RunStatus.COMPLETED, RunStatus.FAILED}:
            raise ValueError("finish requires COMPLETED or FAILED")
        await self._op(run_id, "finish", status=status.value)

    async def expire_terminal_run(self, run_id, *, admin_token: str, ttl_s: int = 86400):
        if not 1 <= ttl_s <= 31536000:
            raise ValueError("ttl_s outside supported range")
        await self._op(run_id, "expire", admin_hash=self._admin_hash(admin_token), ttl_s=ttl_s)
