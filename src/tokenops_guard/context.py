import base64
import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from .exceptions import AuthorizationError
from .models import RunStatus, StrictModel


class RunContext(StrictModel):
    run_id: UUID = Field(default_factory=uuid4)
    parent_run_id: UUID | None = None
    agent_id: str = Field(default="coordinator", min_length=1, max_length=120)
    step_id: str = Field(default_factory=lambda: str(uuid4()), max_length=120)
    trace_id: UUID = Field(default_factory=uuid4)
    budget_usd: Decimal = Field(gt=0)
    max_tokens: int = Field(gt=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: RunStatus = RunStatus.RUNNING

    def child(self, agent_id: str) -> "RunContext":
        """An agent changes attribution, never run identity or budget."""
        return RunContext.model_validate(
            {**self.model_dump(), "agent_id": agent_id, "step_id": str(uuid4())}
        )

    def step(self) -> "RunContext":
        return self.child(self.agent_id)


_context: ContextVar[RunContext | None] = ContextVar("tokenops_run", default=None)


def current_run() -> RunContext:
    ctx = _context.get()
    if ctx is None:
        raise RuntimeError("A verified RunContext must be bound before a governed call")
    return ctx


@contextmanager
def bind_run(context: RunContext):
    token = _context.set(context)
    try:
        yield context
    finally:
        _context.reset(token)


class RunContextSigner:
    """Signed, expiring, principal-bound HTTP/queue capability for trusted workers.

    The authenticating service supplies principal from its authenticated identity,
    never from an untrusted header. This signs a reference, not a new budget.
    """

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("Transport secret must contain at least 32 bytes")
        self.secret = secret

    def headers(self, ctx: RunContext, principal: str, ttl_s: int = 300) -> dict[str, str]:
        if not principal or not 1 <= ttl_s <= 3600:
            raise ValueError("Expected principal and ttl_s in 1..3600")
        payload = json.dumps(
            {
                "run_id": str(ctx.run_id),
                "agent_id": ctx.agent_id,
                "principal": principal,
                "exp": int(time.time()) + ttl_s,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return {"X-TokenOps-Context": encoded + "." + signature}

    async def from_headers(self, headers: dict[str, str], principal: str, ledger) -> RunContext:
        try:
            value = {k.lower(): v for k, v in headers.items()}["x-tokenops-context"]
            if len(value) > 4096:
                raise ValueError("Oversized capability")
            encoded, signature = value.split(".")
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError("Invalid signature")
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if payload["principal"] != principal or payload["exp"] <= time.time():
                raise ValueError("Expired or wrong audience")
            run_id = UUID(payload["run_id"])
            return await ledger.get_context(run_id, payload["agent_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthorizationError("Invalid run capability") from exc
