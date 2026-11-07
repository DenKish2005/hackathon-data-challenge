import asyncio
import json
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


@pytest.mark.parametrize("kind", ["ollama", "openai_compatible"])
async def test_switching_wire_limits_and_per_call_usage(kind):
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "contract-model"
        assert body["messages"] == [{"role": "user", "content": "Return JSON"}]
        if kind == "ollama":
            assert request.url.path == "/api/chat"
            assert body["stream"] is False
            assert body["format"] == {"type": "object"}
            assert body["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": 256}
            data = {
                "done": True,
                "done_reason": "stop",
                "message": {"content": '{"ok": true}'},
                "prompt_eval_count": 25,
                "eval_count": 10,
            }
        else:
            assert body["max_tokens"] == 256
            assert body["response_format"] == {"type": "json_object"}
            data = {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 25, "completion_tokens": 10, "total_tokens": 35},
            }
        return httpx.Response(200, json=data)

    provider = build_provider(
        Settings(
            llm_provider=kind,
            llm_base_url="http://127.0.0.1:11434",
            llm_model="contract-model",
            llm_api_key="synthetic",
            external_data_allowed=True,
            llm_context_size=8192,
            llm_output_limit=256,
            llm_timeout=7,
            llm_concurrency=1,
            llm_attempts=2,
        )
    )
    provider.transport = httpx.MockTransport(handler)
    result = await provider.generate(
        [{"role": "user", "content": "Return JSON"}], {"type": "object"}
    )
    assert result == {"ok": True}
    assert result.metadata["usage"]["input_tokens"] == 25
    assert result.metadata["usage"]["output_tokens"] == 10
    assert result.metadata["duration_seconds"] >= 0
    assert provider.timeout == 7
    assert provider.configuration()["output_limit"] == 256


@pytest.mark.parametrize("provider_class", [OllamaProvider, OpenAICompatibleProvider])
@pytest.mark.parametrize("failure", ["json", "array", "truncated", "empty", "shape", "nan"])
async def test_bad_generation_never_becomes_success(provider_class, failure):
    content = {
        "json": "{",
        "array": "[]",
        "truncated": "{}",
        "empty": "",
        "shape": None,
        "nan": '{"value": NaN}',
    }[failure]
    if provider_class is OllamaProvider:
        data = {
            "done": True,
            "done_reason": "length" if failure == "truncated" else "stop",
            "message": {"content": content},
        }
    else:
        data = {
            "choices": [
                {
                    "finish_reason": "length" if failure == "truncated" else "stop",
                    "message": {"content": content},
                }
            ]
        }
    provider = provider_class(
        "http://localhost:11434",
        "test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)),
    )
    with pytest.raises(ProviderError, match="invalid or incomplete"):
        await provider.generate([], {})


@pytest.mark.parametrize("provider_class", [OllamaProvider, OpenAICompatibleProvider])
async def test_context_rejected_before_http(provider_class):
    def unexpected(request):
        raise AssertionError("Oversized context reached provider")

    provider = provider_class(
        "http://localhost:11434",
        "test",
        context_size=4096,
        output_limit=1024,
        transport=httpx.MockTransport(unexpected),
    )
    with pytest.raises(ProviderError, match="context"):
        await provider.generate([{"content": "Ж" * 3000}], {})


async def test_ollama_schema_grammar_is_not_charged_as_prompt_text():
    messages = [{"role": "user", "content": "Return JSON"}]
    schema = {"type": "object", "properties": {"value": {"enum": ["x" * 10000]}}}

    def handler(request):
        body = json.loads(request.content)
        assert body["messages"] == messages
        assert body["format"] == schema
        assert body["options"]["num_ctx"] == 4096
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 120,
                "message": {"content": '{"value": "synthetic"}'},
            },
        )

    provider = OllamaProvider(
        "http://localhost:11434",
        "test",
        context_size=4096,
        output_limit=512,
        transport=httpx.MockTransport(handler),
    )
    assert await provider.generate(messages, schema) == {"value": "synthetic"}


async def test_ollama_reported_prompt_overflow_is_rejected():
    provider = OllamaProvider(
        "http://localhost:11434",
        "test",
        context_size=4096,
        output_limit=512,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 3800,
                    "message": {"content": '{"value": "synthetic"}'},
                },
            )
        ),
    )
    with pytest.raises(ProviderError, match="context"):
        await provider.generate([{"role": "user", "content": "Return JSON"}], {})


def test_remote_ollama_needs_data_permission():
    with pytest.raises(ValueError, match="permission"):
        build_provider(
            Settings(llm_provider="ollama", llm_base_url="https://remote.test", llm_model="test")
        )
