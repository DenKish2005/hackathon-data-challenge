from time import perf_counter

from cqa.infra.llm.base import HTTPProvider, ProviderError


class OpenAICompatibleProvider(HTTPProvider):
    async def _generate(self, messages, schema):
        self.check_context(messages, schema)
        started = perf_counter()
        data = await self.post(
            "/chat/completions",
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": self.output_limit,
                "response_format": {"type": "json_object"},
            },
        )
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete output")
            usage = data.get("usage") or {}
            return self.decoded(
                choice["message"]["content"],
                {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                },
                started,
            )
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "Provider returned invalid or incomplete output", "invalid_output"
            ) from exc
