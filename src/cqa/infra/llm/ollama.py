from time import perf_counter

from cqa.infra.llm.base import HTTPProvider, ProviderError


class OllamaProvider(HTTPProvider):
    def configuration(self):
        return {**super().configuration(), "num_ctx": self.context_size}

    async def generate(self, messages, schema):
        self.check_context(messages, schema)
        started = perf_counter()
        data = await self.post(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_ctx": self.context_size,
                    "num_predict": self.output_limit,
                },
            },
        )
        try:
            if (
                not isinstance(data, dict)
                or data.get("done") is not True
                or data.get("done_reason") != "stop"
            ):
                raise ValueError("Incomplete output")
            return self.decoded(
                data["message"]["content"],
                {
                    "input_tokens": data.get("prompt_eval_count"),
                    "output_tokens": data.get("eval_count"),
                },
                started,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Provider returned invalid or incomplete output") from exc
