import json

from cqa.infra.llm.base import HTTPProvider, ProviderError


class OllamaProvider(HTTPProvider):
    def configuration(self):
        return {**super().configuration(), "num_ctx": 65536}

    async def generate(self, messages, schema):
        # Reject large inputs rather than letting Ollama silently truncate the transcript.
        if len(json.dumps(messages).encode()) + len(json.dumps(schema).encode()) + 9000 > 65536:
            raise ProviderError("Input exceeds configured safe model context")
        data = await self.post(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_ctx": 65536, "num_predict": 8000},
            },
        )
        try:
            if data.get("done") is not True or data.get("done_reason") == "length":
                raise ValueError("Incomplete output")
            return json.loads(data["message"]["content"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Provider returned invalid or incomplete output") from exc
