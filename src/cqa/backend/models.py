"""Foundation tables use their own namespace; legacy data remains untouched."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC).isoformat()


def identifier():
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "cqa_conversations"
    conversation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    dataset_group_id: Mapped[str] = mapped_column(String(100), index=True)
    channel: Mapped[str]
    language: Mapped[str]
    audio_url: Mapped[str | None]
    original_payload: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[str] = mapped_column(default=now)


class Message(Base):
    __tablename__ = "cqa_messages"
    message_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey(Conversation.conversation_id), index=True
    )
    message_index: Mapped[int]
    speaker: Mapped[str]
    timestamp_original: Mapped[str]
    text: Mapped[str]


class Checklist(Base):
    __tablename__ = "cqa_checklists"
    checklist_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    criteria: Mapped[list] = mapped_column(JSON)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(default=now)


class EvaluationJob(Base):
    __tablename__ = "cqa_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["checklist_id", "checklist_version"],
            ["cqa_checklists.checklist_id", "cqa_checklists.version"],
        ),
    )
    job_id: Mapped[str] = mapped_column(primary_key=True, default=identifier)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey(Conversation.conversation_id))
    checklist_id: Mapped[str]
    checklist_version: Mapped[int]
    status: Mapped[str] = mapped_column(default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class Evaluation(Base):
    __tablename__ = "cqa_evaluations"
    evaluation_id: Mapped[str] = mapped_column(primary_key=True, default=identifier)
    job_id: Mapped[str] = mapped_column(ForeignKey(EvaluationJob.job_id), unique=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey(Conversation.conversation_id))
    checklist_id: Mapped[str]
    checklist_version: Mapped[int]
    evaluator_name: Mapped[str]
    model_name: Mapped[str]
    prompt_version: Mapped[str]
    result_json: Mapped[dict] = mapped_column(JSON)
    is_mock: Mapped[bool] = mapped_column(Boolean)
    review_revision: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now)


class Appeal(Base):
    __tablename__ = "cqa_appeals"
    appeal_id: Mapped[str] = mapped_column(primary_key=True, default=identifier)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey(Evaluation.evaluation_id), index=True)
    criterion_id: Mapped[str]
    comment: Mapped[str]
    status: Mapped[str] = mapped_column(default="open")
    reviewer_decision: Mapped[str | None]
    reviewer_reason: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class ReviewHistory(Base):
    __tablename__ = "cqa_reviews"
    review_id: Mapped[str] = mapped_column(primary_key=True, default=identifier)
    appeal_id: Mapped[str] = mapped_column(ForeignKey(Appeal.appeal_id))
    evaluation_id: Mapped[str] = mapped_column(ForeignKey(Evaluation.evaluation_id), index=True)
    original_result: Mapped[dict] = mapped_column(JSON)
    final_result: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str]
    reason: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)
