"""Database models. Checklist snapshots and evaluations are append-only."""
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.engine import make_url
from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "cqa_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(160), index=True)
    dataset_group_id: Mapped[str] = mapped_column(String(60), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    language: Mapped[str] = mapped_column(String(3))
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_payload: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.message_index")
    __table_args__ = (UniqueConstraint("dataset_group_id", "conversation_id"),)


class Message(Base):
    __tablename__ = "cqa_messages"
    message_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    conversation_ref: Mapped[int] = mapped_column(ForeignKey("cqa_conversations.id"), index=True)
    message_index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(20))
    timestamp_original: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    __table_args__ = (UniqueConstraint("conversation_ref", "message_index"),)


class Checklist(Base):
    __tablename__ = "cqa_checklists"
    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSON)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("checklist_id", "version"),)


class EvaluationJob(Base):
    __tablename__ = "cqa_evaluation_jobs"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_ref: Mapped[int] = mapped_column(ForeignKey("cqa_conversations.id"))
    checklist_ref: Mapped[int] = mapped_column(ForeignKey("cqa_checklists.id"))
    checklist_id: Mapped[str] = mapped_column(String(100))
    checklist_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Evaluation(Base):
    __tablename__ = "cqa_evaluations"
    evaluation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_ref: Mapped[int] = mapped_column(ForeignKey("cqa_conversations.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("cqa_evaluation_jobs.job_id"), unique=True)
    checklist_id: Mapped[str] = mapped_column(String(100))
    checklist_version: Mapped[int] = mapped_column(Integer)
    evaluator_name: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    result_json: Mapped[dict] = mapped_column(JSON)
    is_mock: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Appeal(Base):
    __tablename__ = "cqa_appeals"
    appeal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("cqa_evaluations.evaluation_id"))
    criterion_id: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    reviewer_decision: Mapped[str | None] = mapped_column(String(30))
    reviewer_reason: Mapped[str | None] = mapped_column(Text)
    final_answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReviewHistory(Base):
    __tablename__ = "cqa_review_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("cqa_appeals.appeal_id"), index=True)
    initial_evaluation_json: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(30))
    final_answer: Mapped[str | None] = mapped_column(Text)
    reviewer_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCache(Base):
    __tablename__ = "cqa_llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_session_factory(database_url: str):
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    if database_url.startswith("sqlite") and ":memory:" not in database_url:
        db_path = make_url(database_url).database
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False), engine
