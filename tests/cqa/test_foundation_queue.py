import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from cqa.agents.classifier import BasicClassifier
from cqa.agents.extractor import BasicExtractor
from cqa.backend.config import Settings
from cqa.backend.models import Evaluation, EvaluationJob, Message
from cqa.backend.schemas import ChecklistCreate, DatasetEnvelope, EvaluationCreate
from cqa.backend.services.checklist_service import create_checklist
from cqa.backend.services.dataset_importer import import_dataset
from cqa.backend.services.evaluation_jobs import create_job, inputs
from cqa.infra.orchestrator.pipeline import (
    MockEvaluator,
    Pipeline,
    ProviderEvaluator,
    validate_result,
)
from cqa.infra.orchestrator.queue import Worker, worker_lock
from cqa.workspace import default_checklist

from .test_foundation_data import dataset_payload


def setup_job(database, pipeline=None, settings=None):
    pipeline = pipeline or Pipeline(MockEvaluator())
    settings = settings or Settings()
    import_dataset(database, DatasetEnvelope.model_validate(dataset_payload()))
    create_checklist(
        database, ChecklistCreate(checklist_id="official", criteria=default_checklist())
    )
    request = EvaluationCreate(
        conversation_id="synthetic-0", checklist_id="official", checklist_version=1
    )
    return (
        create_job(database, pipeline, settings, request),
        Worker(database, pipeline, settings),
        request,
    )


async def test_jobs_are_deduplicated_and_results_are_durable(database):
    job, worker, request = setup_job(database)
    assert job.status == "pending"
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(
            pool.map(
                lambda _: create_job(database, worker.pipeline, worker.settings, request), range(8)
            )
        )
    assert {j.job_id for j in jobs} == {job.job_id}
    assert await worker.process_one()
    assert not await worker.process_one()
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "completed"
        result = session.scalar(select(Evaluation))
        assert result.is_mock is True
        assert result.result_json["is_mock"] is True
        assert result.result_json["score"] == 0
        assert result.result_json["findings"][0]["message_ids"] == []
    assert create_job(database, worker.pipeline, worker.settings, request).job_id == job.job_id


async def test_recovery_does_not_duplicate_or_lose_jobs(database):
    job, worker, request = setup_job(database)
    assert worker.claim() == job.job_id
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "running"
    replacement = Worker(database, worker.pipeline, worker.settings)
    replacement.recover()
    assert await replacement.process_one()
    replacement.recover()
    assert not await replacement.process_one()
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Evaluation)) == 1
    with worker_lock(database), pytest.raises(RuntimeError, match="Another CQA worker"):
        with worker_lock(database):
            pass


@pytest.mark.parametrize("mode", ["timeout", "error"])
async def test_failure_and_explicit_retry(database, mode):
    class FailingEvaluator(MockEvaluator):
        async def evaluate_conversation(self, conversation, checklist):
            if mode == "timeout":
                await asyncio.sleep(1)
            raise RuntimeError("private transcript sig=secret")

    job, worker, request = setup_job(database, Pipeline(FailingEvaluator()), Settings(timeout=0.02))
    assert await worker.process_one()
    with database.sessions() as session:
        failed = session.get(EvaluationJob, job.job_id)
        assert failed.status == "failed"
        assert "secret" not in failed.error_message
        assert session.scalar(select(func.count()).select_from(Evaluation)) == 0
    assert create_job(database, worker.pipeline, worker.settings, request).status == "failed"
    retry = request.model_copy(update={"retry_failed": True})
    assert create_job(database, worker.pipeline, worker.settings, retry).status == "pending"
    worker.pipeline.evaluator = MockEvaluator()
    assert await worker.process_one()
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "completed"


async def test_pipeline_validates_evidence_na_and_steps_and_optional_stages(database):
    pipeline = Pipeline(
        MockEvaluator(),
        extractor=BasicExtractor(),
        classifier=BasicClassifier(),
        categories={"ru": {"language": "RU"}},
    )
    job, worker, request = setup_job(database, pipeline)
    with database.sessions() as session:
        conversation, checklist = inputs(session, request.conversation_id, "official", 1)
    result = await MockEvaluator().evaluate_conversation(conversation, checklist)
    result.findings[0].answer = "N/A"
    with pytest.raises(ValueError, match="applicability"):
        validate_result(result, conversation, checklist)
    result.findings[0].answer = "Нет"
    result.findings[3].answer = 3
    with pytest.raises(ValueError, match="scale"):
        validate_result(result, conversation, checklist)
    result.findings[3].answer = 5
    result.findings[0].checked_message_ids = ["invented"]
    with pytest.raises(ValueError, match="reference"):
        validate_result(result, conversation, checklist)
    assert await worker.process_one()
    with database.sessions() as session:
        body = session.scalar(select(Evaluation)).result_json
        assert body["stages"]["classification"]["labels"] == ["ru"]


def test_cache_covers_model_prompt_checklist_and_source(database):
    job, worker, request = setup_job(database)
    worker.settings.prompt_version = "new-prompt"
    assert create_job(database, worker.pipeline, worker.settings, request).job_id != job.job_id
    worker.settings.prompt_version = "foundation-v1"
    worker.pipeline.evaluator.model = "another-model"
    assert create_job(database, worker.pipeline, worker.settings, request).job_id != job.job_id
    worker.pipeline.evaluator.model = "synthetic-mock-v1"
    with database.sessions.begin() as session:
        message = session.scalar(select(Message).where(Message.conversation_id == "synthetic-0"))
        message.text = "Changed source text invalidates cache"
    assert create_job(database, worker.pipeline, worker.settings, request).job_id != job.job_id
    create_checklist(
        database,
        ChecklistCreate(checklist_id="official", base_version=1, criteria=default_checklist()),
    )
    newer = request.model_copy(update={"checklist_version": 2})
    assert create_job(database, worker.pipeline, worker.settings, newer).job_id != job.job_id


async def test_restart_rejects_pending_job_when_model_configuration_changed(database):
    job, worker, request = setup_job(database)
    worker.pipeline.evaluator.model = "new-model-after-restart"
    assert await worker.process_one()
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "failed"
        assert session.scalar(select(func.count()).select_from(Evaluation)) == 0
    replacement = create_job(database, worker.pipeline, worker.settings, request)
    assert replacement.job_id != job.job_id
    assert await worker.process_one()
    with database.sessions() as session:
        assert session.get(EvaluationJob, replacement.job_id).status == "completed"


async def test_shutdown_cancellation_and_restart_limit(database):
    job, worker, request = setup_job(database)
    worker.claim()
    with database.sessions.begin() as session:
        session.get(EvaluationJob, job.job_id).attempts = 3
    worker.recover()
    with database.sessions() as session:
        assert session.get(EvaluationJob, job.job_id).status == "failed"


async def test_provider_adapter_reuses_ai_contract_and_verifies_quotes(database):
    import json

    job, worker, request = setup_job(database)
    with database.sessions() as session:
        conversation, checklist = inputs(session, request.conversation_id, "official", 1)

    class FakeProvider:
        model = "contract-model"
        is_mock = True

        def configuration(self):
            return {"provider": "test", "model": self.model}

        async def generate(self, messages, schema):
            content = json.loads(messages[-1]["content"])
            assert content["channel"] == "agent chat"
            assert content["checklist_id"] == "official"
            assert content["messages"][1]["role"] == "bot"
            first = content["messages"][0]
            assert first["id"] == conversation.messages[0].message_id
            return {
                "summary": "Synthetic contract test",
                "results": [
                    {
                        "criterionId": c.id,
                        "answer": min(c.scale) if c.type == "scale" else "Нет",
                        "reason": "Synthetic contract answer, no real assessment",
                        "evidenceId": first["id"],
                        "quote": first["text"],
                        "checkedMessageIds": [m["id"] for m in content["messages"]],
                        "confidence": 0.0,
                    }
                    for c in checklist.criteria
                ],
            }

    pipeline = Pipeline(ProviderEvaluator(FakeProvider()))
    result = await pipeline.run(conversation, checklist)
    assert result["is_mock"] is True
    assert result["metadata"]["quotes"]["1"] == conversation.messages[0].text
