"""Small provider contract with bounded retries and redacted failures."""

import asyncio
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class RedactHTTPLogs(logging.Filter):
    def filter(self, record):
        record.msg, record.args = "HTTP request (URL and payload redacted)", ()
        return True


# httpx normally logs complete signed URLs at INFO.
logging.getLogger("httpx").addFilter(RedactHTTPLogs())


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    model: str
    is_mock: bool

    def configuration(self) -> dict: ...

    async def generate(self, messages: list[dict], schema: dict) -> dict: ...


async def request_json(client, method, url, *, attempts=3, backoff=0.25, **kwargs):
    """No HTTP exception text/URLs/bodies in logs or the public error."""
    for attempt in range(attempts):
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
                raise ProviderError("Upstream unavailable or timed out") from exc
            await asyncio.sleep(backoff * 2**attempt)
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Upstream rejected request or returned invalid JSON") from exc
    raise ProviderError("Upstream attempts exhausted")


class HTTPProvider:
    is_mock = False

    def __init__(self, base_url, model, *, api_key="", concurrency=2, timeout=60, transport=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.semaphore = asyncio.Semaphore(concurrency)

    def configuration(self):
        # Hash used internally, never returned by the API. No API key in persistent cache material.
        return {
            "provider": type(self).__name__,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": 0,
            "output_limit": 8000,
        }

    async def post(self, path, body):
        async with (
            self.semaphore,
            httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            return await request_json(
                client, "POST", self.base_url + path, json=body, headers=headers
            )
