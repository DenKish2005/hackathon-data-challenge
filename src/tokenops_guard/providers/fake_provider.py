import asyncio
import hashlib

from ..config import ModelPrice
from ..models import LLMResponse, Usage


class FakeProvider:
    """No network. Predictable usage and stable, non-private demonstration output."""

    def __init__(
        self,
        *,
        input_tokens: int = 100,
        output_tokens: int = 100,
        delay_s: float = 0.01,
        error: Exception | None = None,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.delay_s = delay_s
        self.error = error
        self.calls: list[dict] = []

    def estimate_input(self, prompt: str, price: ModelPrice) -> int:
        return self.input_tokens

    async def complete(
        self, *, prompt: str, price: ModelPrice, max_output_tokens: int, call_id: str
    ) -> LLMResponse:
        self.calls.append(
            {"model": price.model_id, "max_output_tokens": max_output_tokens, "call_id": call_id}
        )
        await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return LLMResponse(
            text="fake-result-" + hashlib.sha256(prompt.encode()).hexdigest()[:12],
            usage=Usage(
                input_tokens=self.input_tokens,
                output_tokens=min(self.output_tokens, max_output_tokens),
            ),
            provider="fake",
            model=price.model_id,
            request_id="fake-" + call_id,
        )
