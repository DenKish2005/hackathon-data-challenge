"""Small provider contract with bounded retries and redacted failures."""

import asyncio
import json
import logging
from contextvars import ContextVar
from time import perf_counter
from typing import Protocol
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)
call_metrics = ContextVar("cqa_call_metrics", default=None)
active_call = ContextVar("cqa_active_call", default=None)


class RedactHTTPLogs(logging.Filter):
    def filter(self, record):
        record.msg, record.args = "HTTP request (URL and payload redacted)", ()
        return True


# httpx normally logs complete signed URLs at INFO.
logging.getLogger("httpx").addFilter(RedactHTTPLogs())


class ProviderError(RuntimeError):
    def __init__(self, message, code="provider_error"):
        super().__init__(message)
        self.code = code


class GeneratedJSON(dict):
    """Keep the existing dict contract; metadata belongs to this call, not shared state."""

    def __init__(self, payload, metadata):
        super().__init__(payload)
        self.metadata = metadata


class Provider(Protocol):
    model: str
    is_mock: bool

    def configuration(self) -> dict: ...

    async def generate(self, messages: list[dict], schema: dict) -> dict: ...


async def request_json(client, method, url, *, attempts=3, backoff=0.25, metrics=None, **kwargs):
    """No HTTP exception text/URLs/bodies in logs or the public error."""
    for attempt in range(attempts):
        if metrics is not None:
            metrics["http_attempts"] = attempt + 1
            metrics["retries"] = attempt
        try:
            response = await client.request(method, url, **kwargs)
            code = response.status_code
            logger.info("upstream attempt=%d status=%d", attempt + 1, code)
            if code == 429 or 500 <= code < 600:
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * 2**attempt)
                    continue
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.info("upstream attempt=%d transport_error", attempt + 1)
            if attempt + 1 == attempts:
                raise ProviderError("Upstream unavailable or timed out", "transport_error") from exc
            await asyncio.sleep(backoff * 2**attempt)
        except (httpx.HTTPError, ValueError) as exc:
            code = "invalid_json" if isinstance(exc, ValueError) else "http_error"
            raise ProviderError("Upstream rejected request or returned invalid JSON", code) from exc
    raise ProviderError("Upstream attempts exhausted")


class HTTPProvider:
    is_mock = False

    def __init__(
        self,
        base_url,
        model,
        *,
        api_key="",
        concurrency=2,
        timeout=60,
        transport=None,
        context_size=65536,
        output_limit=8000,
        attempts=3,
    ):
        parts = urlsplit(base_url)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or not 1 <= concurrency <= 16
            or timeout <= 0
            or not 1 <= attempts <= 5
            or output_limit < 1
            or context_size <= output_limit + 1024
        ):
            raise ValueError("Invalid provider endpoint or limits")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.semaphore = asyncio.Semaphore(concurrency)
        self.context_size, self.output_limit, self.attempts = context_size, output_limit, attempts

    def configuration(self):
        # Hash used internally, never returned by the API. No API key in persistent cache material.
        return {
            "provider": type(self).__name__,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": 0,
            "output_limit": self.output_limit,
            "context_size": self.context_size,
            "adapter_version": 2,
        }

    def check_context(self, messages, schema):
        # UTF-8 byte count is a conservative bound, not a reported token measurement.
        size = len(json.dumps(messages, ensure_ascii=False).encode())
        size += len(json.dumps(schema, ensure_ascii=False).encode())
        if size + self.output_limit + 1024 > self.context_size:
            raise ProviderError("Input exceeds configured safe model context", "context_limit")

    async def generate(self, messages, schema):
        metrics = {
            "provider": type(self).__name__,
            "model": self.model,
            "http_attempts": 0,
            "retries": 0,
            "usage": {},
        }
        trace = call_metrics.get()
        if trace is not None:
            trace.append(metrics)
        token = active_call.set(metrics)
        started = perf_counter()
        try:
            result = await self._generate(messages, schema)
            metrics.update(result.metadata)
            metrics["status"] = "completed"
            return result
        except asyncio.CancelledError:
            metrics.update(status="cancelled", error_code="cancelled")
            raise
        except ProviderError as exc:
            metrics.update(status="failed", error_code=exc.code)
            raise
        finally:
            metrics["duration_seconds"] = round(perf_counter() - started, 6)
            active_call.reset(token)

    def decoded(self, content, usage, started):
        try:
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            # Reject NaN/Infinity even before the downstream strict domain schema.
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ProviderError(
                "Provider returned invalid or incomplete output", "invalid_output"
            ) from exc
        return GeneratedJSON(
            payload,
            {
                "model": self.model,
                "provider": type(self).__name__,
                "duration_seconds": round(perf_counter() - started, 6),
                "usage": {
                    key: value for key, value in usage.items() if type(value) is int and value >= 0
                },
            },
        )

    async def post(self, path, body):
        started = perf_counter()
        async with (
            self.semaphore,
            httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            metrics = active_call.get()
            if metrics is not None:
                metrics["provider_wait_seconds"] = round(perf_counter() - started, 6)
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            return await request_json(
                client,
                "POST",
                self.base_url + path,
                json=body,
                headers=headers,
                attempts=self.attempts,
                metrics=metrics,
            )
