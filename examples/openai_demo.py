"""Optional PAID example; never used by automated tests or the default demo."""

import asyncio
import os

from redis.asyncio import Redis

from tokenops_guard import GovernedLLMClient, RedisLedger, bind_run, load_settings
from tokenops_guard.observability import console_summary
from tokenops_guard.providers import OpenAIProvider


async def main():
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY to run this optional paid example")
    settings = load_settings(pricing="config/openai_pricing.yaml")
    redis = Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=5
    )
    ledger = RedisLedger(redis)
    provider = OpenAIProvider()
    client = GovernedLLMClient(ledger, settings, {"openai": provider})
    try:
        handle = await ledger.create_run(settings)
        with bind_run(handle.context):
            response = await client.complete(
                "Explain atomic budget reservations in two sentences.", max_output_tokens=256
            )
        print(response.text)
        snapshot = await ledger.get_run_status(handle.context.run_id)
        if snapshot.status in {"RUNNING", "STEERED"}:
            await ledger.finish(handle.context.run_id)
        print(console_summary(await ledger.get_run_status(handle.context.run_id)))
    finally:
        await client.aclose()
        await provider.aclose()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
