"""Append-only review snapshots; immutable original model output."""

from copy import deepcopy

from sqlalchemy import select, update

from cqa.backend.models import Appeal, Evaluation, ReviewHistory, now
from cqa.backend.services.dataset_importer import Conflict
from cqa.backend.services.evaluation_jobs import inputs
from cqa.infra.orchestrator.pipeline import EvaluationResult, Finding, validate_result


def final_result(session, evaluation):
    latest = session.scalar(
        select(ReviewHistory)
        .where(ReviewHistory.evaluation_id == evaluation.evaluation_id)
        .order_by(ReviewHistory.revision.desc())
        .limit(1)
    )
    return latest.final_result if latest else evaluation.result_json


def create_appeal(db, request):
    with db.sessions.begin() as session:
        evaluation = session.get(Evaluation, request.evaluation_id)
        if not evaluation:
            raise LookupError()
        if request.criterion_id not in {
            f["criterion_id"] for f in evaluation.result_json["findings"]
        }:
            raise ValueError("Unknown criterion")
        appeal = Appeal(**request.model_dump())
        session.add(appeal)
    return appeal


def review_appeal(db, pipeline, appeal_id, request):
    with db.sessions.begin() as session:
        appeal = session.get(Appeal, appeal_id)
        if not appeal:
            raise LookupError()
        if appeal.status != "open":
            raise Conflict("Appeal has already been reviewed")
        evaluation = session.get(Evaluation, appeal.evaluation_id)
        if evaluation.review_revision != request.base_revision:
            raise Conflict("Evaluation has changed; reload its review_revision")
        previous = final_result(session, evaluation)
        final = deepcopy(previous)
        if request.decision == "accepted":
            if (
                request.replacement is None
                or request.replacement.criterion_id != appeal.criterion_id
            ):
                raise ValueError("Provide replacement for the appealed criterion")
            conversation, checklist = inputs(
                session,
                evaluation.conversation_id,
                evaluation.checklist_id,
                evaluation.checklist_version,
            )
            findings = [
                request.replacement
                if f["criterion_id"] == appeal.criterion_id
                else Finding.model_validate(f)
                for f in final["findings"]
            ]
            validated = validate_result(
                EvaluationResult(findings=findings, is_mock=evaluation.is_mock),
                conversation,
                checklist,
            )
            final["findings"] = [f.model_dump(mode="json") for f in validated.findings]
            final.update(pipeline.scorer.score(checklist, validated))
        changed = session.execute(
            update(Evaluation)
            .where(
                Evaluation.evaluation_id == evaluation.evaluation_id,
                Evaluation.review_revision == request.base_revision,
            )
            .values(review_revision=request.base_revision + 1)
        )
        if changed.rowcount != 1:
            raise Conflict("Concurrent review; reload and retry")
        appeal.status = "reviewed"
        appeal.reviewer_decision = request.decision
        appeal.reviewer_reason = request.reason
        appeal.updated_at = now()
        review = ReviewHistory(
            appeal_id=appeal_id,
            evaluation_id=evaluation.evaluation_id,
            revision=request.base_revision + 1,
            original_result=deepcopy(evaluation.result_json),
            final_result=final,
            decision=request.decision,
            reason=request.reason,
        )
        session.add(review)
    return appeal
