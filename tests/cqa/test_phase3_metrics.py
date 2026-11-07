import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from cqa.backend.models import Evaluation, JobMetrics
from cqa.infra.llm.base import ProviderError, call_metrics
from cqa.infra.llm.ollama import OllamaProvider
from cqa.infra.orchestrator.pipeline import Pipeline, ProviderEvaluator

from .test_foundation_queue import setup_job


async def test_retries_usage_load_time_and_invalid_output_are_payload_free():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": "private invalid JSON"},
                "prompt_eval_count": 17,
                "eval_count": 4,
                "load_duration": 250000000,
            },
        )

    provider = OllamaProvider(
        "http://localhost:11434", "test", attempts=2, transport=httpx.MockTransport(handler)
    )
    trace = []
    token = call_metrics.set(trace)
    try:
        with pytest.raises(ProviderError):
            await provider.generate([], {})
    finally:
        call_metrics.reset(token)
    assert trace[0]["http_attempts"] == 2
    assert trace[0]["retries"] == 1
    assert trace[0]["load_duration_seconds"] == 0.25
    assert trace[0]["usage"] == {"input_tokens": 17, "output_tokens": 4}
    assert trace[0]["error_code"] == "invalid_output"
    assert "private" not in json.dumps(trace)


async def test_failed_job_metrics_survive_without_saving_an_evaluation(database):
    provider = OllamaProvider(
        "http://localhost:11434",
        "test",
        attempts=1,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"done": False})),
    )
    job, worker, _ = setup_job(database, Pipeline(ProviderEvaluator(provider)))
    await worker.process_one()
    with database.sessions() as session:
        metrics = session.scalar(select(JobMetrics)).metrics
        assert session.scalar(select(Evaluation)) is None
        assert metrics["status"] == "failed"
        assert metrics["error_code"] == "invalid_output"
        assert metrics["queue_seconds"] >= 0
        assert len(metrics["calls"]) == 1


async def test_concurrent_calls_have_separate_metrics():
    async def run(number):
        trace = []
        token = call_metrics.set(trace)
        try:
            provider = OllamaProvider(
                "http://localhost:11434",
                str(number),
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200,
                        json={
                            "done": True,
                            "done_reason": "stop",
                            "message": {"content": "{}"},
                            "eval_count": number,
                        },
                    )
                ),
            )
            await provider.generate([], {})
            return trace
        finally:
            call_metrics.reset(token)

    traces = await asyncio.gather(run(1), run(2))
    assert [t[0]["usage"]["output_tokens"] for t in traces] == [1, 2]
