import os
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from tokenops_guard.config import Settings, load_settings
from tokenops_guard.ledger.redis_ledger import RedisLedger


@pytest.fixture
def settings():
    return load_settings()


def configured(settings: Settings, **changes) -> Settings:
    """Validated nested overrides, never model_copy's unvalidated update."""
    data = settings.model_dump(mode="json")
    for path, value in changes.items():
        keys = path.split("__")
        target = data
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return Settings.model_validate(data)


@pytest_asyncio.fixture
async def ledger():
    url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    redis = Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=2)
    try:
        await redis.ping()
    except Exception as exc:
        await redis.aclose()
        pytest.fail(
            f"Real Redis required at TEST_REDIS_URL: {type(exc).__name__}; "
            "run docker compose up -d redis first"
        )
    prefix = "test-tokenops-" + uuid4().hex
    store = RedisLedger(redis, prefix=prefix)
    yield store
    # Isolated test namespace only: never FLUSHDB or touch another run's keys.
    keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()
