from openai import AsyncOpenAI

from ..config import ModelPrice
from ..exceptions import ProviderNotDispatchedError
from ..models import LLMResponse, Usage


class OpenAIProvider:
    """Non-streaming, single-message TEXT chat; no tools, images or hidden retries.

    Byte count + framing allowance is a conservative estimate, not a provider
    contractual bound. Actual usage includes reasoning tokens in completion_tokens.
    Cache categories use configured rates; worst-case admission uses the input multiplier.
    """

    def __init__(self, client: AsyncOpenAI | None = None):
        # Enforce retry=0 even on injected SDK clients; never retry an ambiguous charge.
        self.client = (client or AsyncOpenAI()).with_options(max_retries=0)

    def estimate_input(self, prompt: str, price: ModelPrice) -> int:
        return len(prompt.encode("utf-8")) + 64

    async def complete(
        self, *, prompt: str, price: ModelPrice, max_output_tokens: int, call_id: str
    ) -> LLMResponse:
        if price.provider != "openai" or max_output_tokens < 1:
            raise ProviderNotDispatchedError("Unsupported provider or token cap")
        response = await self.client.chat.completions.create(
            model=price.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=max_output_tokens,
            service_tier="default",
            stream=False,
            # Correlation only. This is NOT a provider idempotency guarantee.
            extra_headers={"X-Client-Request-Id": call_id},
        )
        if response.usage is None:
            raise ValueError("Missing provider usage; billing must be reconciled")
        details = response.usage.prompt_tokens_details
        if details and details.audio_tokens:
            raise ValueError("Audio billing is outside this text-only adapter")
        return LLMResponse(
            text=response.choices[0].message.content or "",
            usage=Usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cached_input_tokens=(details.cached_tokens or 0) if details else 0,
                cache_write_input_tokens=(details.cache_write_tokens or 0) if details else 0,
            ),
            provider="openai",
            model=price.model_id,
            request_id=response.id,
        )

    async def aclose(self):
        await self.client.close()
