"""Content-addressed jobs with DB uniqueness and bounded explicit retry."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cqa.backend.models import Checklist, Conversation, Evaluation, EvaluationJob, Message
from cqa.backend.schemas import ChecklistView, ConversationDetail, MessageView
from cqa.service import RULES


def inputs(session, conversation_id, checklist_id, version):
    conversation = session.get(Conversation, conversation_id)
    checklist = session.get(Checklist, (checklist_id, version))
    if not conversation or not checklist:
        raise LookupError("Conversation or checklist version not found")
    messages = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.message_index)
    ).all()
    detail = ConversationDetail(
        **{
            key: getattr(conversation, key)
            for key in ConversationDetail.model_fields
            if key != "messages"
        },
        messages=[MessageView.model_validate(m) for m in messages],
    )
    return detail, ChecklistView.model_validate(checklist)


def job_key(conversation, checklist, pipeline, settings):
    content = {
        "conversation": conversation.model_dump(mode="json"),
        "checklist": checklist.model_dump(mode="json"),
        "pipeline": pipeline.configuration(),
        "prompt_version": settings.prompt_version,
        "rules": RULES,
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def create_job(db, pipeline, settings, request):
    with db.sessions() as session:
        conversation, checklist = inputs(
            session, request.conversation_id, request.checklist_id, request.checklist_version
        )
        key = job_key(conversation, checklist, pipeline, settings)
        existing = session.scalar(
            select(EvaluationJob)
            .where((EvaluationJob.cache_key == key) | EvaluationJob.cache_key.startswith(key + ":"))
            .order_by(EvaluationJob.created_at.desc())
            .limit(1)
        )
        if existing and not request.force:
            if request.retry_failed and existing.status == "failed":
                existing.status = "pending"
                existing.error_message = None
                existing.attempts = 0
                session.commit()
            return existing
        job = EvaluationJob(
            cache_key=key if not request.force else key + ":" + uuid4().hex,
            conversation_id=conversation.conversation_id,
            checklist_id=checklist.checklist_id,
            checklist_version=checklist.version,
        )
        session.add(job)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            job = session.scalar(select(EvaluationJob).where(EvaluationJob.cache_key == key))
            if job is None:
                raise
        return job


def job_view(session, job):
    evaluation_id = session.scalar(
        select(Evaluation.evaluation_id).where(Evaluation.job_id == job.job_id)
    )
    return {
        key: getattr(job, key)
        for key in (
            "job_id",
            "conversation_id",
            "checklist_id",
            "checklist_version",
            "status",
            "error_message",
            "attempts",
            "created_at",
            "updated_at",
        )
    } | {"evaluation_id": evaluation_id}
