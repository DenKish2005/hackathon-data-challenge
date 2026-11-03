import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from redis.asyncio import Redis

from tokenops_guard.context import bind_run
from tokenops_guard.exceptions import (
    BudgetStoreUnavailableError,
    ConcurrencyLimitError,
    DuplicateCallError,
    ProviderNotDispatchedError,
)
from tokenops_guard.ledger.redis_ledger import RedisLedger
from tokenops_guard.models import LLMResponse, RunStatus, Usage
from tokenops_guard.providers import FakeProvider, OpenAIProvider
from tokenops_guard.wrapper import GovernedLLMClient

from .conftest import configured


async def test_timeout_keeps_uncertain_reserve(ledger, settings):
    settings = configured(settings, reliability__request_timeout_s=0.04)
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=0.2)
    call_id = str(uuid4())
    with bind_run(ctx), pytest.raises(TimeoutError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete(
            "private", call_id=call_id
        )
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved > 0 and s.active == 0 and s.status == RunStatus.HALTED
    assert (await ledger.get_call(ctx.run_id, call_id))["state"] == "UNKNOWN"


async def test_cancel_keeps_uncertain_reserve(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=5)
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    with bind_run(ctx):
        task = asyncio.create_task(client.complete("cancel"))
    for _ in range(100):
        if fake.calls:
            break
        await asyncio.sleep(0.01)
    assert fake.calls
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await client.aclose()
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved > 0 and s.active == 0 and s.status == RunStatus.HALTED


async def test_store_down_blocks_dispatch(settings):
    redis = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.05, socket_timeout=0.05)
    ledger = RedisLedger(redis)
    from tokenops_guard.context import RunContext

    ctx = RunContext(budget_usd="2", max_tokens=1000)
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    try:
        with bind_run(ctx), pytest.raises(BudgetStoreUnavailableError):
            await client.complete("blocked")
        assert not fake.calls
    finally:
        await client.aclose()
        await redis.aclose()


async def test_known_not_dispatched_releases_reserve(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(error=ProviderNotDispatchedError("local validation"))
    with bind_run(ctx), pytest.raises(ProviderNotDispatchedError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("local error")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.reserved == s.spent == s.active == 0 and s.status == RunStatus.RUNNING


async def test_unexpected_error_and_cost_calculation_failure_hold_reserve(ledger, settings):
    class InvalidUsageProvider(FakeProvider):
        async def complete(self, **kwargs):
            return LLMResponse(
                text="bad",
                usage=Usage(input_tokens=10**9, output_tokens=10**9),
                provider="fake",
                model=kwargs["price"].model_id,
            )

    ctx = (await ledger.create_run(settings)).context
    with bind_run(ctx), pytest.raises(ValueError):
        await GovernedLLMClient(ledger, settings, {"fake": InvalidUsageProvider()}).complete(
            "bad usage"
        )
    assert (await ledger.get_run_status(ctx.run_id)).reserved > 0
    assert (await ledger.get_run_status(ctx.run_id)).status == RunStatus.HALTED


async def test_concurrency_reject(ledger, settings):
    settings = configured(
        settings,
        policies__concurrency_cap__max_parallel_calls=1,
        policies__concurrency_cap__action="REJECT",
    )
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=0.12)
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    with bind_run(ctx):
        results = await asyncio.gather(
            *(client.complete(f"p-{i}") for i in range(5)), return_exceptions=True
        )
    assert sum(isinstance(r, ConcurrencyLimitError) for r in results) == 4
    assert len(fake.calls) == 1
    assert (await ledger.get_run_status(ctx.run_id)).active == 0


async def test_concurrency_queue_serializes(ledger, settings):
    settings = configured(
        settings,
        policies__concurrency_cap__max_parallel_calls=1,
        policies__concurrency_cap__action="QUEUE",
    )
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=0.03)
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    with bind_run(ctx):
        results = await asyncio.gather(*(client.complete(f"p-{i}") for i in range(5)))
    assert len(results) == len(fake.calls) == 5
    assert (await ledger.get_run_status(ctx.run_id)).spent == 1000000


async def test_live_heartbeat_prevents_false_expiry(ledger, settings):
    settings = configured(settings, reliability__lease_s=0.15, reliability__heartbeat_s=0.03)
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(delay_s=0.35)
    with bind_run(ctx):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("long request")
    s = await ledger.get_run_status(ctx.run_id)
    assert s.spent == 200000 and s.reserved == 0 and s.status == RunStatus.RUNNING


async def test_wrapper_retry_same_call_never_dispatches_twice(ledger, settings):
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider()
    client = GovernedLLMClient(ledger, settings, {"fake": fake})
    call = str(uuid4())
    with bind_run(ctx):
        await client.complete("first", call_id=call)
        with pytest.raises(DuplicateCallError):
            await client.complete("first", call_id=call)
    assert len(fake.calls) == 1
    assert (await ledger.get_run_status(ctx.run_id)).spent == 200000


async def test_logs_and_audit_do_not_contain_prompt_or_provider_exception(ledger, settings, caplog):
    ctx = (await ledger.create_run(settings)).context
    fake = FakeProvider(error=RuntimeError("SECRET_PROVIDER_KEY"))
    with bind_run(ctx), pytest.raises(RuntimeError):
        await GovernedLLMClient(ledger, settings, {"fake": fake}).complete("PRIVATE_PROMPT")
    audit = json.dumps(await ledger.get_run_events(ctx.run_id)) + caplog.text
    assert "PRIVATE_PROMPT" not in audit and "SECRET_PROVIDER_KEY" not in audit


async def test_openai_sdk_request_and_usage_without_paid_api(settings):
    captured = []

    async def handler(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "hello"},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )

    sdk = AsyncOpenAI(
        api_key="test-not-a-real-key",
        max_retries=2,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    provider = OpenAIProvider(sdk)
    price = settings.models["primary_model"].model_copy(update={"provider": "openai"})
    try:
        response = await provider.complete(
            prompt="hello", price=price, max_output_tokens=24, call_id=str(uuid4())
        )
        body = json.loads(captured[0].content)
        assert body["max_completion_tokens"] == 24 and body["service_tier"] == "default"
        assert response.usage == Usage(input_tokens=12, output_tokens=8)
        assert provider.client.max_retries == 0
    finally:
        await provider.aclose()


async def test_openai_sdk_has_no_hidden_network_retry(settings):
    from openai import InternalServerError

    attempts = []

    async def handler(request):
        attempts.append(request)
        return httpx.Response(500, json={"error": {"message": "simulated", "type": "server_error"}})

    sdk = AsyncOpenAI(
        api_key="fake", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    provider = OpenAIProvider(sdk)
    price = settings.models["primary_model"].model_copy(update={"provider": "openai"})
    try:
        with pytest.raises(InternalServerError):
            await provider.complete(
                prompt="one", price=price, max_output_tokens=10, call_id=str(uuid4())
            )
        assert len(attempts) == 1
    finally:
        await provider.aclose()
