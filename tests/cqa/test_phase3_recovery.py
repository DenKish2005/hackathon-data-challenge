import asyncio
import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from cqa.backend.config import Settings
from cqa.backend.main import create_app
from cqa.backend.models import Evaluation, EvaluationJob
from cqa.backend.schemas import ChecklistCreate
from cqa.backend.services.checklist_service import create_checklist
from cqa.backend.services.evaluation_jobs import create_job
from cqa.infra.orchestrator.pipeline import MockEvaluator, Pipeline
from cqa.workspace import default_checklist

from .test_foundation_queue import setup_job


async def test_checklist_change_during_job_keeps_old_snapshot(database):
    entered, release = asyncio.Event(), asyncio.Event()

    class Paused(MockEvaluator):
        async def evaluate_conversation(self, conversation, checklist):
            entered.set()
            await release.wait()
            return await super().evaluate_conversation(conversation, checklist)

    job, worker, request = setup_job(database, Pipeline(Paused()))
    task = asyncio.create_task(worker.process_one())
    await entered.wait()
    criteria = default_checklist()
    criteria[0] = {**criteria[0], "title": "New version"}
    create_checklist(
        database, ChecklistCreate(checklist_id="official", base_version=1, criteria=criteria)
    )
    newer = create_job(
        database,
        worker.pipeline,
        worker.settings,
        request.model_copy(update={"checklist_version": 2}),
    )
    assert newer.job_id != job.job_id
    release.set()
    await task
    await worker.process_one()
    with database.sessions() as session:
        results = session.scalars(select(Evaluation).order_by(Evaluation.checklist_version)).all()
        assert [r.checklist_version for r in results] == [1, 2]


async def test_cancelled_worker_recovers_without_false_result(database):
    entered = asyncio.Event()

    class Paused(MockEvaluator):
        async def evaluate_conversation(self, conversation, checklist):
            entered.set()
            await asyncio.Event().wait()

    job, worker, _ = setup_job(database, Pipeline(Paused()))
    task = asyncio.create_task(worker.process_one())
    await entered.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    with database.sessions() as session:
        assert session.scalar(select(Evaluation)) is None
        assert session.get(EvaluationJob, job.job_id).status == "running"
    worker.pipeline.evaluator = MockEvaluator()
    # Test fixture's replacement has the same configuration; real changes require a new job.
    worker.recover()
    assert await worker.process_one()
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "completed"


def test_readiness_reports_model_outage_without_leaking_endpoint(tmp_path, monkeypatch):
    original = httpx.AsyncClient

    def handler(request):
        raise httpx.ConnectError("private upstream details", request=request)

    monkeypatch.setattr(
        "cqa.backend.main.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'ready.db'}",
            llm_provider="ollama",
            llm_model="test",
            llm_base_url="http://localhost:11434",
        ),
        worker_enabled=False,
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "model_unavailable"
        assert "private" not in json.dumps(response.json())
