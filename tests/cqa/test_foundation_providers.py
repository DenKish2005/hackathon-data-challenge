import asyncio
import logging

import httpx
import pytest

from cqa.backend.config import Settings
from cqa.infra.llm import build_provider
from cqa.infra.llm.base import ProviderError, request_json
from cqa.infra.llm.ollama import OllamaProvider
from cqa.infra.llm.openai_compatible import OpenAICompatibleProvider


async def test_retry_temporary_errors_and_redact_signed_urls(caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response([429, 503, 200][len(calls) - 1], json={"ok": True})

    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await request_json(
                client, "GET", "https://private.test/path?sig=secret", backoff=0
            ) == {"ok": True}
    assert len(calls) == 3
    assert "sig=" not in caplog.text
    assert "secret" not in caplog.text
    assert "private.test" not in caplog.text


@pytest.mark.parametrize("code,attempts", [(401, 1), (403, 1), (400, 1), (500, 3), (429, 3)])
async def test_bounded_failures(code, attempts):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code, text="private error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="Upstream") as error:
            await request_json(client, "GET", "https://example.test/?sig=secret", backoff=0)
    assert "secret" not in str(error.value)
    assert len(calls) == attempts


async def test_timeout_retries_are_bounded():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="timed out"):
            await request_json(client, "GET", "https://example.test", backoff=0)
    assert len(calls) == 3


async def test_openai_and_ollama_contracts_and_concurrency():
    active = peak = 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        if request.url.path == "/v1/chat/completions":
            assert request.headers["authorization"] == "Bearer test"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"findings": []}'}}
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"done": True, "done_reason": "stop", "message": {"content": '{"findings": []}'}},
        )

    provider = OpenAICompatibleProvider(
        "https://example.test/v1",
        "test",
        api_key="test",
        concurrency=2,
        transport=httpx.MockTransport(handler),
    )
    results = await asyncio.gather(*(provider.generate([], {}) for _ in range(6)))
    assert results == [{"findings": []}] * 6
    assert peak == 2
    local = OllamaProvider("http://localhost:11434", "test", transport=httpx.MockTransport(handler))
    assert await local.generate([], {}) == {"findings": []}
    with pytest.raises(ProviderError, match="context"):
        await local.generate([{"content": "x" * 70000}], {})


def test_external_provider_requires_explicit_configuration_and_permission():
    assert build_provider(Settings()).is_mock
    with pytest.raises(ValueError, match="permission"):
        build_provider(Settings(llm_provider="openai_compatible", external_data_allowed=False))
    with pytest.raises(ValueError, match="LLM_MODEL"):
        build_provider(Settings(llm_provider="ollama"))
