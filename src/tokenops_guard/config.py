import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from .models import MAX_MONEY, MAX_TOKENS, StrictModel


class BudgetConfig(StrictModel):
    max_usd: Decimal = Field(default=Decimal("2"), gt=0, le=Decimal(MAX_MONEY) / 1000000)
    max_tokens: int = Field(default=100000, gt=0, le=MAX_TOKENS)

    @model_validator(mode="after")
    def microdollars(self):
        if self.max_usd * 1000000 != int(self.max_usd * 1000000):
            raise ValueError("Budget must be an exact integer number of microdollars")
        return self


class CostBudget(StrictModel):
    enabled: Literal[True] = True
    action: Literal["HALT"] = "HALT"


class WorstCase(StrictModel):
    enabled: bool = True
    action: Literal["SHRINK_OR_HALT"] = "SHRINK_OR_HALT"


class CostGuard(StrictModel):
    enabled: bool = True
    threshold: Decimal = Field(default=Decimal("0.80"), gt=0, le=1, decimal_places=4)
    action: Literal["STEER"] = "STEER"


class StepCap(StrictModel):
    enabled: bool = True
    max_steps: int = Field(default=100, ge=1, le=1000000)
    max_calls: int = Field(default=100, ge=1, le=1000000)


class ConcurrencyCap(StrictModel):
    enabled: bool = True
    max_parallel_calls: int = Field(default=5, ge=1, le=10000)
    action: Literal["QUEUE", "REJECT"] = "REJECT"
    queue_timeout_s: float = Field(default=5, gt=0, le=3600)


class ProgressGuard(StrictModel):
    enabled: bool = True
    max_repeated_actions: int = Field(default=4, ge=2, le=20)
    max_pattern_length: int = Field(default=8, ge=1, le=16)


class Policies(StrictModel):
    cost_budget: CostBudget = Field(default_factory=CostBudget)
    pre_call_worst_case: WorstCase = Field(default_factory=WorstCase)
    cost_guard: CostGuard = Field(default_factory=CostGuard)
    step_cap: StepCap = Field(default_factory=StepCap)
    concurrency_cap: ConcurrencyCap = Field(default_factory=ConcurrencyCap)
    progress_guard: ProgressGuard = Field(default_factory=ProgressGuard)


class Routing(StrictModel):
    primary: str = "primary_model"
    fallback: str = "economy_model"


class Reliability(StrictModel):
    fail_closed: Literal[True] = True
    request_timeout_s: float = Field(default=30, gt=0, le=3600)
    lease_s: float = Field(default=60, ge=0.1, le=86400)
    heartbeat_s: float = Field(default=10, ge=0.02, le=3600)

    @model_validator(mode="after")
    def timing(self):
        if self.heartbeat_s >= self.lease_s / 2:
            raise ValueError("heartbeat_s must be less than half lease_s")
        return self


class ObservabilityConfig(StrictModel):
    enabled: bool = True


class ModelPrice(StrictModel):
    provider: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=120)
    input_usd_per_million: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    output_usd_per_million: Decimal = Field(gt=0, le=1000000, decimal_places=6)
    cached_input_usd_per_million: Decimal | None = Field(
        default=None, ge=0, le=1000000, decimal_places=6
    )
    cache_write_usd_per_million: Decimal | None = Field(
        default=None, ge=0, le=1000000, decimal_places=6
    )
    input_billing_multiplier: Decimal = Field(default=Decimal("1"), ge=1, le=100)
    max_input_tokens: int = Field(default=16000, ge=1, le=MAX_TOKENS)
    max_output_tokens: int = Field(default=4096, ge=1, le=MAX_TOKENS)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def safe_arithmetic(self):
        input_ceiling = self.input_usd_per_million * self.input_billing_multiplier
        for rate in (self.cached_input_usd_per_million, self.cache_write_usd_per_million):
            if rate is not None and rate > input_ceiling:
                raise ValueError("Input billing multiplier must bound every input category")
        worst = (
            self.max_input_tokens * self.input_usd_per_million * self.input_billing_multiplier
            + self.max_output_tokens * self.output_usd_per_million
        )
        if worst > MAX_MONEY:
            raise ValueError("Per-call cost exceeds supported integer range")
        return self


class Settings(StrictModel):
    enabled: Literal[True] = True
    redis_url: str = "redis://localhost:6379/0"
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    policies: Policies = Field(default_factory=Policies)
    model_routing: Routing = Field(default_factory=Routing)
    reliability: Reliability = Field(default_factory=Reliability)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    models: dict[str, ModelPrice]

    @model_validator(mode="after")
    def routing_valid(self):
        if (
            self.model_routing.primary not in self.models
            or self.model_routing.fallback not in self.models
        ):
            raise ValueError("Routing refers to an unknown model")
        p, f = (self.models[self.model_routing.primary], self.models[self.model_routing.fallback])
        if (
            f.input_usd_per_million * f.input_billing_multiplier
            > p.input_usd_per_million * p.input_billing_multiplier
            or f.output_usd_per_million > p.output_usd_per_million
        ):
            raise ValueError("Fallback must not be more expensive than primary")
        return self

    def fingerprint(self) -> str:
        # Connection URL and logging preferences are local; admission rules are shared.
        raw = json.dumps(
            self.model_dump(mode="json", exclude={"redis_url", "observability"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def load_settings(
    policies: str | Path = "config/policies.yaml", pricing: str | Path = "config/model_pricing.yaml"
) -> Settings:
    base = yaml.safe_load(Path(policies).read_text(encoding="utf-8"))["tokenops"]
    base["models"] = yaml.safe_load(Path(pricing).read_text(encoding="utf-8"))["models"]
    if url := os.environ.get("REDIS_URL"):
        base["redis_url"] = url
    return Settings.model_validate(base)
