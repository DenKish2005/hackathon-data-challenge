from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from cqa.backend.models import Appeal, Evaluation, ReviewHistory
from cqa.backend.services.appeal_service import create_appeal, final_result, review_appeal
from cqa.backend.services.dataset_importer import Conflict
from cqa.infra.orchestrator.pipeline import Finding

from .test_foundation_queue import setup_job


class AppealInput(BaseModel):
    evaluation_id: str
    criterion_id: str
    comment: str = "Please check"


async def test_reviews_preserve_original_and_accumulate_changes(database):
    job, worker, request = setup_job(database)
    await worker.process_one()
    with database.sessions() as session:
        evaluation = session.scalar(select(Evaluation))
        evaluation_id = evaluation.evaluation_id
        refs = evaluation.result_json["findings"][0]["checked_message_ids"]
    for revision, criterion_id in enumerate(("1", "2")):
        appeal = create_appeal(
            database, AppealInput(evaluation_id=evaluation_id, criterion_id=criterion_id)
        )
        request = SimpleNamespace(
            decision="accepted",
            reason="Confirmed by reviewer",
            base_revision=revision,
            replacement=Finding(
                criterion_id=criterion_id,
                answer="Да",
                explanation="Human review of source transcript",
                message_ids=refs,
            ),
        )
        reviewed = review_appeal(database, worker.pipeline, appeal.appeal_id, request)
        assert reviewed.status == "reviewed"
        with pytest.raises(Conflict):
            review_appeal(database, worker.pipeline, appeal.appeal_id, request)
    with database.sessions() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        assert evaluation.result_json["score"] == 0
        assert final_result(session, evaluation)["score"] == 25
        assert evaluation.review_revision == 2
        history = session.scalars(select(ReviewHistory).order_by(ReviewHistory.revision)).all()
        assert [h.final_result["score"] for h in history] == [10, 25]
        assert all(h.original_result["score"] == 0 for h in history)
    another = create_appeal(database, AppealInput(evaluation_id=evaluation_id, criterion_id="3"))
    with pytest.raises(Conflict):
        review_appeal(
            database,
            worker.pipeline,
            another.appeal_id,
            SimpleNamespace(decision="rejected", reason="No change", base_revision=0),
        )
    assert (
        review_appeal(
            database,
            worker.pipeline,
            another.appeal_id,
            SimpleNamespace(decision="rejected", reason="No change", base_revision=2),
        ).status
        == "reviewed"
    )
    with database.sessions() as session:
        assert final_result(session, session.get(Evaluation, evaluation_id))["score"] == 25


async def test_invalid_review_is_atomic(database):
    job, worker, request = setup_job(database)
    await worker.process_one()
    with database.sessions() as session:
        evaluation_id = session.scalar(select(Evaluation.evaluation_id))
    appeal = create_appeal(database, AppealInput(evaluation_id=evaluation_id, criterion_id="1"))
    with pytest.raises(ValueError):
        review_appeal(
            database,
            worker.pipeline,
            appeal.appeal_id,
            SimpleNamespace(
                decision="accepted",
                reason="Invalid N/A",
                base_revision=0,
                replacement=Finding(
                    criterion_id="1",
                    answer="N/A",
                    explanation="Not allowed",
                    checked_message_ids=["fake"],
                    na_reason="No",
                ),
            ),
        )
    with database.sessions() as session:
        assert session.get(Appeal, appeal.appeal_id).status == "open"
        assert session.get(Evaluation, evaluation_id).review_revision == 0
