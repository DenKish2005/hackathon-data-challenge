from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MONEY = 10**12
MAX_TOKENS = 10**9


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    STEERED = "STEERED"
    HALTED = "HALTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Usage(StrictModel):
    input_tokens: int = Field(ge=0, le=MAX_TOKENS)
    output_tokens: int = Field(ge=0, le=MAX_TOKENS)
    cached_input_tokens: int = Field(default=0, ge=0, le=MAX_TOKENS)
    cache_write_input_tokens: int = Field(default=0, ge=0, le=MAX_TOKENS)

    @model_validator(mode="after")
    def categories(self):
        if self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens:
            raise ValueError("Cache categories must be disjoint subsets of input_tokens")
        return self


class LLMResponse(StrictModel):
    text: str
    usage: Usage
    model: str
    provider: str
    request_id: str | None = None


class RunSnapshot(StrictModel):
    run_id: UUID
    budget: int
    max_tokens: int
    spent: int = 0
    reserved: int = 0
    reserved_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    steps: int = 0
    active: int = 0
    status: RunStatus
    halt_reason: str = ""
    steered: bool = False

    @property
    def remaining(self) -> int:
        return self.budget - self.spent - self.reserved


class PolicySteerEvent(StrictModel):
    run_id: UUID
    model: str
    policy_triggered: str = "cost_guard"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
