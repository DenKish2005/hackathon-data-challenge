from time import perf_counter

from cqa.infra.llm.base import HTTPProvider, ProviderError, active_call


class OllamaProvider(HTTPProvider):
    def configuration(self):
        return {**super().configuration(), "num_ctx": self.context_size}

    def check_context(self, messages, schema):
        # Ollama receives `format` as a sampler grammar, separately from the chat.
        # Count the complete messages and output reserve, without charging grammar
        # bytes as prompt tokens. The JSON-object provider includes its schema in text.
        super().check_context(messages, {})

    async def _generate(self, messages, schema):
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
        if isinstance(data, dict) and active_call.get() is not None:
            metrics = active_call.get()
            metrics["usage"] = {
                key: data[source]
                for key, source in (
                    ("input_tokens", "prompt_eval_count"),
                    ("output_tokens", "eval_count"),
                )
                if type(data.get(source)) is int and data[source] >= 0
            }
            for field in (
                "load_duration",
                "prompt_eval_duration",
                "eval_duration",
                "total_duration",
            ):
                value = data.get(field)
                if type(value) is int and value >= 0:
                    metrics[field + "_seconds"] = value / 1_000_000_000
        reported_tokens = data.get("prompt_eval_count") if isinstance(data, dict) else None
        if (
            type(reported_tokens) is int
            and reported_tokens + self.output_limit >= self.context_size
        ):
            raise ProviderError("Input exceeds configured safe model context", "context_limit")
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
            raise ProviderError(
                "Provider returned invalid or incomplete output", "invalid_output"
            ) from exc
