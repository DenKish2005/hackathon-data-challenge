"""Freedom CQA backend. Launch: uvicorn cqa.backend.main:app --reload"""
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from cqa.backend.config import Settings
from cqa.backend.models import (Appeal, Checklist, Conversation, Evaluation, EvaluationJob,
                                ReviewHistory, make_session_factory)
from cqa.backend.schemas import (AppealCreate, AppealReviewCreate, ChecklistCreate,
                                 DatasetImport, EvaluationCreate)
from cqa.backend.checklists import OFFICIAL, validate_criteria, validate_answer
from cqa.backend.services import (conversation_out, digest, download_dataset, import_dataset,
                                  load_dataset_file)
from cqa.infra.pipeline import PipelineWorker


def create_app(settings: Settings | None = None, *, evaluator=None):
    settings = settings or Settings()
    sessions, engine = make_session_factory(settings.database_url)
    with sessions() as db:
        if not db.scalar(select(Checklist).where(Checklist.checklist_id == "official")):
            db.add(Checklist(checklist_id="official", version=1, criteria=OFFICIAL, sections=[]))
            db.commit()
    worker = PipelineWorker(sessions, evaluator=evaluator, poll_seconds=settings.worker_poll_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await worker.start()
        try:
            yield
        finally:
            await worker.stop()
            engine.dispose()

    app = FastAPI(title="Freedom Broker CQA Backend", version="0.1.0", lifespan=lifespan)
    app.state.sessions = sessions
    app.state.worker = worker
    app.add_middleware(CORSMiddleware, allow_origins=[v.strip() for v in settings.cors_origins.split(",") if v.strip()],
                       allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

    def session():
        with sessions() as db:
            yield db

    def lookup_conversation(db, cid, group_id=None):
        statement = select(Conversation).where(Conversation.conversation_id == cid)
        if group_id:
            statement = statement.where(Conversation.dataset_group_id == group_id)
        results = db.scalars(statement).all()
        if not results:
            raise HTTPException(404, "Conversation not found")
        if len(results) > 1:
            raise HTTPException(409, "Specify group_id to disambiguate conversation")
        return results[0]

    def checklist_out(c):
        return {"checklist_id": c.checklist_id, "version": c.version, "criteria": c.criteria,
                "sections": c.sections, "created_at": c.created_at.isoformat()}

    def get_checklist(db, cid, version=None):
        q = select(Checklist).where(Checklist.checklist_id == cid)
        if version is not None:
            q = q.where(Checklist.version == version)
        else:
            q = q.order_by(Checklist.version.desc())
        c = db.scalar(q.limit(1))
        if not c:
            raise HTTPException(404, "Checklist/version not found")
        return c

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "cqa-backend", "mode": "mock" if evaluator is None else "custom"}

    @app.post("/api/datasets/import")
    async def import_api(req: DatasetImport, db=Depends(session)):
        if req.source == "payload":
            payload = req.payload
        elif req.source == "local":
            if req.group_id == "CONTROL":
                raise HTTPException(422, "CONTROL requires an explicitly configured API URL or payload")
            payload = load_dataset_file(settings.dataset_path)
        else:
            url = settings.dev_api_url if req.group_id == "DEV" else settings.control_api_url
            payload = await download_dataset(url)
        return import_dataset(db, payload, expected_group=req.group_id)

    @app.get("/api/conversations")
    def list_conversations(group_id: str | None = None, language: str | None = None,
                           channel: str | None = None, limit: int = Query(100, ge=1, le=200),
                           offset: int = Query(0, ge=0), db=Depends(session)):
        stmt = select(Conversation)
        if group_id:
            stmt = stmt.where(Conversation.dataset_group_id == group_id)
        if language:
            stmt = stmt.where(Conversation.language == language)
        if channel:
            stmt = stmt.where(Conversation.channel == channel)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.order_by(Conversation.id).limit(limit).offset(offset)).all()
        return {"items": [conversation_out(x) for x in rows], "total": total, "limit": limit, "offset": offset}

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, group_id: str | None = None, db=Depends(session)):
        c = lookup_conversation(db, conversation_id, group_id)
        db.refresh(c, attribute_names=["messages"])
        return conversation_out(c, include_messages=True)

    @app.get("/api/checklists")
    def list_checklists(db=Depends(session)):
        return {"items": [checklist_out(c) for c in db.scalars(select(Checklist).order_by(Checklist.checklist_id, Checklist.version)).all()]}

    @app.post("/api/checklists", status_code=201)
    def create_checklist(req: ChecklistCreate, db=Depends(session)):
        validate_criteria(req.criteria)
        latest = db.scalar(select(Checklist).where(Checklist.checklist_id == req.checklist_id).order_by(Checklist.version.desc()))
        if latest and req.expected_version != latest.version:
            raise HTTPException(409, "expected_version must match current checklist version")
        if not latest and req.expected_version is not None:
            raise HTTPException(409, "Checklist does not exist; omit expected_version")
        c = Checklist(checklist_id=req.checklist_id, version=(latest.version+1) if latest else 1,
                      criteria=req.criteria, sections=req.sections)
        db.add(c)
        db.commit()
        return checklist_out(c)

    @app.get("/api/checklists/{checklist_id}")
    def current_checklist(checklist_id: str, db=Depends(session)):
        return checklist_out(get_checklist(db, checklist_id))

    @app.get("/api/checklists/{checklist_id}/versions/{version}")
    def version_checklist(checklist_id: str, version: int, db=Depends(session)):
        return checklist_out(get_checklist(db, checklist_id, version))

    @app.post("/api/evaluations", status_code=202)
    def start_evaluation(req: EvaluationCreate, db=Depends(session)):
        conv = lookup_conversation(db, req.conversation_id, req.group_id)
        checklist = get_checklist(db, req.checklist_id, req.checklist_version)
        fingerprint = digest([conv.original_payload, checklist.checklist_id, checklist.version,
                              getattr(worker.evaluator, "prompt_version", "unspecified"),
                              getattr(worker.evaluator, "model_name", "unspecified")])
        if not req.force:
            candidate = db.scalar(select(EvaluationJob).where(EvaluationJob.conversation_ref == conv.id,
                EvaluationJob.checklist_ref == checklist.id, EvaluationJob.input_hash == fingerprint,
                EvaluationJob.status.in_(["pending", "running", "completed"]))
                .order_by(EvaluationJob.created_at.desc()))
            if candidate:
                return job_out(db, candidate)
        job = EvaluationJob(job_id=str(uuid.uuid4()), conversation_ref=conv.id, checklist_ref=checklist.id,
                            checklist_id=checklist.checklist_id, checklist_version=checklist.version,
                            status="pending", input_hash=fingerprint)
        db.add(job)
        db.commit()
        return job_out(db, job)

    def job_out(db, j):
        ev = db.scalar(select(Evaluation).where(Evaluation.job_id == j.job_id))
        return {"job_id": j.job_id, "status": j.status, "conversation_id": db.get(Conversation, j.conversation_ref).conversation_id,
                "checklist_id": j.checklist_id, "checklist_version": j.checklist_version,
                "evaluation_id": ev.evaluation_id if ev else None,
                "error_message": j.error_message, "created_at": j.created_at.isoformat(),
                "updated_at": j.updated_at.isoformat()}

    @app.get("/api/evaluation-jobs/{job_id}")
    def get_job(job_id: str, db=Depends(session)):
        job = db.get(EvaluationJob, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job_out(db, job)

    @app.get("/api/evaluations/{evaluation_id}")
    def get_evaluation(evaluation_id: str, db=Depends(session)):
        ev = db.get(Evaluation, evaluation_id)
        if not ev:
            raise HTTPException(404, "Evaluation not found")
        return {"evaluation_id": ev.evaluation_id, "conversation_id": db.get(Conversation, ev.conversation_ref).conversation_id,
                "job_id": ev.job_id, "checklist_id": ev.checklist_id, "checklist_version": ev.checklist_version,
                "evaluator_name": ev.evaluator_name, "model_name": ev.model_name, "prompt_version": ev.prompt_version,
                "is_mock": ev.is_mock, "result_json": ev.result_json, "created_at": ev.created_at.isoformat()}

    def appeal_out(db, appeal):
        events = db.scalars(select(ReviewHistory).where(ReviewHistory.appeal_id == appeal.appeal_id).order_by(ReviewHistory.id)).all()
        return {"appeal_id": appeal.appeal_id, "evaluation_id": appeal.evaluation_id, "criterion_id": appeal.criterion_id,
                "comment": appeal.comment, "status": appeal.status, "reviewer_decision": appeal.reviewer_decision,
                "reviewer_reason": appeal.reviewer_reason, "final_answer": json.loads(appeal.final_answer) if appeal.final_answer is not None else None,
                "history": [{"decision": e.decision, "initial_evaluation_json": e.initial_evaluation_json,
                             "final_answer": json.loads(e.final_answer) if e.final_answer is not None else None,
                             "reviewer_reason": e.reviewer_reason, "created_at": e.created_at.isoformat()} for e in events]}

    @app.post("/api/appeals", status_code=201)
    def submit_appeal(req: AppealCreate, db=Depends(session)):
        ev = db.get(Evaluation, req.evaluation_id)
        if not ev:
            raise HTTPException(404, "Evaluation not found")
        if req.criterion_id not in {str(c["id"]) for c in ev.result_json["checklist_snapshot"]["criteria"]}:
            raise HTTPException(422, "Criterion was not in the historical checklist")
        a = Appeal(appeal_id=str(uuid.uuid4()), evaluation_id=req.evaluation_id,
                   criterion_id=req.criterion_id, comment=req.comment)
        db.add(a)
        db.commit()
        return appeal_out(db, a)

    @app.get("/api/appeals/{appeal_id}")
    def get_appeal(appeal_id: str, db=Depends(session)):
        a = db.get(Appeal, appeal_id)
        if not a:
            raise HTTPException(404, "Appeal not found")
        return appeal_out(db, a)

    @app.post("/api/appeals/{appeal_id}/review")
    def review_appeal(appeal_id: str, req: AppealReviewCreate, db=Depends(session)):
        a = db.get(Appeal, appeal_id)
        if not a:
            raise HTTPException(404, "Appeal not found")
        if a.status != "open":
            raise HTTPException(409, "Appeal already reviewed")
        ev = db.get(Evaluation, a.evaluation_id)
        criterion = next(c for c in ev.result_json["checklist_snapshot"]["criteria"] if str(c["id"]) == a.criterion_id)
        if req.decision == "upheld" and not validate_answer(criterion, req.revised_answer):
            raise HTTPException(422, "Revised answer violates historical checklist")
        serialized = json.dumps(req.revised_answer, ensure_ascii=False) if req.revised_answer is not None else None
        db.add(ReviewHistory(appeal_id=a.appeal_id, initial_evaluation_json=ev.result_json,
                             decision=req.decision, final_answer=serialized, reviewer_reason=req.reason))
        a.status = "reviewed"
        a.reviewer_decision = req.decision
        a.reviewer_reason = req.reason
        a.final_answer = serialized
        db.commit()
        return appeal_out(db, a)

    return app


app = create_app()
