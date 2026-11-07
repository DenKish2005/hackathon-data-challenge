"""Run: python -m uvicorn cqa.backend.main:app --host 127.0.0.1 --port 8000."""

import asyncio
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from cqa.backend.config import Settings
from cqa.backend.database import Database
from cqa.backend.models import (
    Appeal,
    Checklist,
    Conversation,
    Evaluation,
    EvaluationJob,
    ReviewHistory,
)
from cqa.backend.requests import AppealCreate, ReviewRequest
from cqa.backend.schemas import (
    ChecklistCreate,
    ChecklistView,
    ConversationDetail,
    ConversationView,
    EvaluationCreate,
    ImportRequest,
    ImportResult,
    JobView,
    Schema,
)
from cqa.backend.services.appeal_service import create_appeal, review_appeal
from cqa.backend.services.checklist_service import create_checklist, seed_checklist
from cqa.backend.services.dataset_importer import Conflict, fetch_organizer, import_dataset
from cqa.backend.services.evaluation_jobs import create_job, inputs, job_view
from cqa.infra.llm import ProviderError, build_provider
from cqa.infra.orchestrator.pipeline import (
    MockEvaluator,
    Pipeline,
    ProviderCritic,
    ProviderEvaluator,
)
from cqa.infra.orchestrator.queue import Worker, worker_lock


class Health(Schema):
    status: str
    provider: str
    model: str
    is_mock: bool


class EvaluationView(Schema):
    evaluation_id: str
    conversation_id: str
    job_id: str
    checklist_id: str
    checklist_version: int
    evaluator_name: str
    model_name: str
    prompt_version: str
    is_mock: bool
    created_at: str
    result_json: dict
    final_result_json: dict
    review_revision: int


class AppealView(Schema):
    appeal_id: str
    evaluation_id: str
    criterion_id: str
    comment: str
    status: str
    reviewer_decision: str | None
    reviewer_reason: str | None
    created_at: str
    updated_at: str


class ReviewView(Schema):
    review_id: str
    appeal_id: str
    evaluation_id: str
    revision: int
    original_result: dict
    final_result: dict
    decision: str
    reason: str
    created_at: str


def create_app(settings=None, pipeline=None, *, worker_enabled=True, transport=None):
    settings = settings or Settings()
    db = Database(settings.database_url)
    if pipeline is None:
        provider = build_provider(settings)
        evaluator = MockEvaluator() if provider.is_mock else ProviderEvaluator(provider)
        pipeline = Pipeline(
            evaluator,
            critic=ProviderCritic(evaluator)
            if not provider.is_mock and settings.critic_enabled
            else None,
        )
    worker = Worker(db, pipeline, settings)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        seed_checklist(db)
        try:
            if worker_enabled:
                with worker_lock(db):
                    worker.recover()
                    tasks = [asyncio.create_task(worker.run()) for _ in range(settings.concurrency)]
                    try:
                        yield
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            else:
                yield
        finally:
            db.engine.dispose()

    app = FastAPI(title="Freedom CQA Backend Foundation", version="1.0.0", lifespan=lifespan)
    app.state.db, app.state.pipeline, app.state.worker = db, pipeline, worker
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        # Pydantic's default "input" field can echo entire confidential transcripts.
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
            },
        )

    for exception, code, detail in (
        (Conflict, 409, None),
        (LookupError, 404, "Resource not found"),
        (ProviderError, 502, "Upstream unavailable or invalid response"),
        (IntegrityError, 409, "Concurrent update conflict; reload and retry"),
        (SQLAlchemyError, 503, "Database unavailable"),
        (ValueError, 422, "Invalid data or evaluation result"),
    ):

        def make_handler(status, message):
            async def handler(request, exc):
                return JSONResponse(status_code=status, content={"detail": message or str(exc)})

            return handler

        app.add_exception_handler(exception, make_handler(code, detail))

    @app.get("/api/health", response_model=Health)
    async def health():
        with db.sessions() as session:
            session.execute(select(1))
        status = "mock" if pipeline.evaluator.is_mock else "configured"
        if settings.llm_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                    response = await client.get(settings.llm_base_url.rstrip("/") + "/api/tags")
                    response.raise_for_status()
                    names = [m["name"] for m in response.json()["models"]]
                status = "ready" if pipeline.evaluator.model in names else "model_unavailable"
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                status = "model_unavailable"
        return Health(
            status=status,
            provider=settings.llm_provider,
            model=pipeline.evaluator.model,
            is_mock=pipeline.evaluator.is_mock,
        )

    @app.post("/api/datasets/import", response_model=ImportResult)
    async def datasets(request: ImportRequest):
        envelope = (
            request.payload
            if request.source == "local"
            else await fetch_organizer(settings, request.group_id, transport)
        )
        return import_dataset(db, envelope)

    @app.get("/api/ready")
    async def ready():
        state = await health()
        return JSONResponse(
            status_code=200 if state.status in ("ready", "mock", "configured") else 503,
            content=state.model_dump(),
        )

    @app.get("/api/conversations", response_model=list[ConversationView])
    def conversations(
        group_id: str | None = None,
        language: Literal["RU", "KZ", "EN"] | None = None,
        channel: Literal["agent chat", "voice call"] | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        query = select(Conversation).order_by(Conversation.conversation_id)
        for column, value in (
            (Conversation.dataset_group_id, group_id),
            (Conversation.language, language),
            (Conversation.channel, channel),
        ):
            if value is not None:
                query = query.where(column == value)
        with db.sessions() as session:
            return session.scalars(query.offset(offset).limit(limit)).all()

    @app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
    def conversation(conversation_id: str):
        with db.sessions() as session:
            detail, _ = inputs(session, conversation_id, "official", 1)
            return detail

    @app.get("/api/checklists", response_model=list[ChecklistView])
    def checklists():
        with db.sessions() as session:
            rows = session.scalars(
                select(Checklist).order_by(Checklist.checklist_id, Checklist.version)
            ).all()
            latest = {row.checklist_id: row for row in rows}
            return list(latest.values())

    @app.post("/api/checklists", response_model=ChecklistView, status_code=201)
    def checklist_create(request: ChecklistCreate):
        return create_checklist(db, request)

    @app.get("/api/checklists/{checklist_id}", response_model=ChecklistView)
    def checklist_latest(checklist_id: str):
        with db.sessions() as session:
            row = session.scalar(
                select(Checklist)
                .where(Checklist.checklist_id == checklist_id)
                .order_by(Checklist.version.desc())
                .limit(1)
            )
            if row is None:
                raise LookupError()
            return row

    @app.get("/api/checklists/{checklist_id}/versions/{version}", response_model=ChecklistView)
    def checklist_version(checklist_id: str, version: int):
        with db.sessions() as session:
            row = session.get(Checklist, (checklist_id, version))
            if row is None:
                raise LookupError()
            return row

    @app.post("/api/evaluations", response_model=JobView, status_code=202)
    def evaluations(request: EvaluationCreate):
        job = create_job(db, pipeline, settings, request)
        with db.sessions() as session:
            return job_view(session, job)

    @app.get("/api/evaluation-jobs/{job_id}", response_model=JobView)
    def evaluation_job(job_id: str):
        with db.sessions() as session:
            job = session.get(EvaluationJob, job_id)
            if job is None:
                raise LookupError()
            return job_view(session, job)

    @app.get("/api/evaluations/{evaluation_id}", response_model=EvaluationView)
    def evaluation(evaluation_id: str):
        with db.sessions() as session:
            row = session.get(Evaluation, evaluation_id)
            if row is None:
                raise LookupError()
            from cqa.backend.services.appeal_service import final_result

            return {
                key: getattr(row, key)
                for key in EvaluationView.model_fields
                if key != "final_result_json"
            } | {"final_result_json": final_result(session, row)}

    @app.post("/api/appeals", response_model=AppealView, status_code=201)
    def appeal_create(request: AppealCreate):
        return create_appeal(db, request)

    @app.get("/api/appeals/{appeal_id}", response_model=AppealView)
    def appeal_get(appeal_id: str):
        with db.sessions() as session:
            appeal = session.get(Appeal, appeal_id)
            if appeal is None:
                raise LookupError()
            return appeal

    @app.post("/api/appeals/{appeal_id}/review", response_model=AppealView)
    def appeal_review(appeal_id: str, request: ReviewRequest):
        return review_appeal(db, pipeline, appeal_id, request)

    @app.get("/api/evaluations/{evaluation_id}/reviews", response_model=list[ReviewView])
    def reviews(evaluation_id: str):
        with db.sessions() as session:
            if session.get(Evaluation, evaluation_id) is None:
                raise LookupError()
            return session.scalars(
                select(ReviewHistory)
                .where(ReviewHistory.evaluation_id == evaluation_id)
                .order_by(ReviewHistory.revision)
            ).all()

    from cqa.backend.compat import install_compat

    install_compat(app, db, pipeline, settings, transport)
    return app


app = create_app()
