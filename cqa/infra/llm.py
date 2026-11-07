"""Optional LLM providers. The pipeline uses MockEvaluator until the AI team plugs in."""
import asyncio
import hashlib
import json
from typing import Protocol

import httpx


class LLMProvider(Protocol):
    async def generate(self, messages: list[dict]) -> dict: ...


class MockProvider:
    async def generate(self, messages: list[dict]) -> dict:
        return {"is_mock": True, "content": "MockProvider did not evaluate user data"}


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str, concurrency: int = 2):
        if not base_url or not model:
            raise ValueError("LLM_BASE_URL and LLM_MODEL must be configured")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.limiter = asyncio.Semaphore(concurrency)

    async def generate(self, messages: list[dict]) -> dict:
        async with self.limiter:
            for attempt in range(3):
                try:
                    headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                    async with httpx.AsyncClient(timeout=40.0, follow_redirects=False) as client:
                        response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json={"model": self.model, "messages": messages})
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * 2**attempt)
                            continue
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, httpx.TransportError):
                    if attempt == 2:
                        raise RuntimeError("LLM transport unavailable") from None
                    await asyncio.sleep(0.5 * 2**attempt)
                except httpx.HTTPStatusError:
                    raise RuntimeError("LLM request rejected") from None
            raise RuntimeError("LLM request exhausted retries")


class OllamaProvider(OpenAICompatibleProvider):
    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "", concurrency: int = 2):
        super().__init__(base_url, "", model, concurrency)


def make_provider(settings):
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "ollama":
        # Only localhost Ollama is allowed by default. Operators must opt in for remote calls.
        if not settings.allow_external_llm and not (settings.llm_base_url.startswith("http://localhost:") or settings.llm_base_url.startswith("http://127.0.0.1:")):
            raise ValueError("Remote LLM calls require CQA_ALLOW_EXTERNAL_LLM=true")
        return OllamaProvider(settings.llm_base_url or "http://localhost:11434/v1", settings.llm_model, settings.max_llm_concurrency)
    if settings.llm_provider == "openai_compatible" and settings.allow_external_llm:
        return OpenAICompatibleProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.max_llm_concurrency)
    raise ValueError("Unknown or unauthorized LLM provider")


def cache_key(conversation_payload, checklist_id, checklist_version, prompt_version, model_name):
    raw = json.dumps([conversation_payload, checklist_id, checklist_version, prompt_version, model_name], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()
