import asyncio
import time

import pytest

from tokenops_guard.context import RunContextSigner, bind_run, current_run
from tokenops_guard.exceptions import AuthorizationError


async def test_context_propagates_to_asyncio_and_child(ledger, settings):
    handle = await ledger.create_run(settings)
    root = handle.context

    async def agent(name):
        assert current_run().run_id == root.run_id
        with bind_run(current_run().child(name)):
            await asyncio.sleep(0)
            return current_run()

    with bind_run(root):
        children = await asyncio.gather(agent("ResearchAgent"), agent("AnalysisAgent"))
        assert current_run() == root
    assert {c.agent_id for c in children} == {"ResearchAgent", "AnalysisAgent"}
    assert all(c.run_id == root.run_id and c.budget_usd == root.budget_usd for c in children)
    with pytest.raises(RuntimeError):
        current_run()


async def test_signed_transport_hydrates_authoritative_budget(ledger, settings):
    handle = await ledger.create_run(settings)
    signer = RunContextSigner(b"x" * 32)
    headers = signer.headers(handle.context.child("remote"), "worker-1")
    ctx = await signer.from_headers(headers, "worker-1", ledger)
    assert ctx.run_id == handle.context.run_id and ctx.agent_id == "remote"
    assert ctx.budget_usd == settings.budget.max_usd
    with pytest.raises(AuthorizationError):
        await signer.from_headers(headers, "worker-2", ledger)
    headers["X-TokenOps-Context"] += "tamper"
    with pytest.raises(AuthorizationError):
        await signer.from_headers(headers, "worker-1", ledger)


async def test_expired_transport(ledger, settings, monkeypatch):
    handle = await ledger.create_run(settings)
    signer = RunContextSigner(b"s" * 32)
    headers = signer.headers(handle.context, "worker", ttl_s=1)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 2)
    with pytest.raises(AuthorizationError):
        await signer.from_headers(headers, "worker", ledger)


async def test_cannot_create_independent_subagent_budget(ledger, settings):
    parent = await ledger.create_run(settings)
    with pytest.raises(ValueError, match="share"):
        await ledger.create_run(settings, parent_run_id=parent.context.run_id)
