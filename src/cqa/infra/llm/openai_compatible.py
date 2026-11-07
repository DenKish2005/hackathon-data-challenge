import json

from cqa.infra.llm.base import HTTPProvider, ProviderError


class OpenAICompatibleProvider(HTTPProvider):
    async def generate(self, messages, schema):
        data = await self.post(
            "/chat/completions",
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 8000,
                "response_format": {"type": "json_object"},
            },
        )
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete output")
            return json.loads(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Provider returned invalid or incomplete output") from exc
