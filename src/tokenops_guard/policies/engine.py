from dataclasses import dataclass

from ..config import Settings
from ..models import RunSnapshot, Usage
from ..pricing import cost_microdollars
from ..providers.base import LLMProvider


@dataclass(frozen=True)
class CallPlan:
    model: str
    input_tokens: int
    max_output_tokens: int
    cost: int

    @property
    def tokens(self):
        return self.input_tokens + self.max_output_tokens


class PolicyEngine:
    """Pure, deterministic routing. Redis remains the final admission authority."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def choose(
        self,
        snapshot: RunSnapshot,
        prompt: str,
        requested_output: int,
        providers: dict[str, LLMProvider],
    ) -> CallPlan | None:
        s = self.settings
        routing = s.model_routing
        candidates = (
            [routing.fallback]
            if snapshot.steered
            else list(dict.fromkeys([routing.primary, routing.fallback]))
        )
        can_shrink = s.policies.pre_call_worst_case.enabled
        for model in candidates:
            price = s.models[model]
            if price.provider not in providers:
                raise ValueError("No registered adapter for " + price.provider)
            inputs = providers[price.provider].estimate_input(prompt, price)
            if inputs < 0 or inputs > price.max_input_tokens:
                continue
            cap = min(requested_output, price.max_output_tokens)
            if snapshot.steered:
                cap = min(cap, 128)
            available_tokens = (
                snapshot.max_tokens
                - snapshot.input_tokens
                - snapshot.output_tokens
                - snapshot.reserved_tokens
            )
            cap = min(cap, available_tokens - inputs) if can_shrink else cap
            # Binary search avoids float money division and rounds exactly as settlement does.
            low, high, best = 1, cap, 0
            while low <= high:
                mid = (low + high) // 2
                cost = cost_microdollars(
                    price, Usage(input_tokens=inputs, output_tokens=mid), worst_case=True
                )
                if cost <= snapshot.remaining and inputs + mid <= available_tokens:
                    best, low = mid, mid + 1
                else:
                    high = mid - 1
            if best and (can_shrink or best == cap):
                return CallPlan(
                    model,
                    inputs,
                    best,
                    cost_microdollars(
                        price, Usage(input_tokens=inputs, output_tokens=best), worst_case=True
                    ),
                )
            if not can_shrink:
                break
        return None
