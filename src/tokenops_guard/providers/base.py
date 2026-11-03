from typing import Protocol

from ..config import ModelPrice
from ..models import LLMResponse


class LLMProvider(Protocol):
    """Adapters must disable hidden retries and bound every billable request.

    estimate_input is a conservative upper bound for the supported text request.
    Cancellation/transport errors mean uncertain billing unless the adapter raises
    ProviderNotDispatchedError with a guarantee that nothing was sent.
    """

    def estimate_input(self, prompt: str, price: ModelPrice) -> int: ...

    async def complete(
        self, *, prompt: str, price: ModelPrice, max_output_tokens: int, call_id: str
    ) -> LLMResponse: ...
