"""Frontend compatibility views over Foundation records; no evaluation engine or store."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import func, select

from cqa.backend.models import (
    Appeal,
    Checklist,
    Conversation,
    Evaluation,
    EvaluationJob,
    ReviewHistory,
    WorkspaceAppeal,
    WorkspaceChecklist,
    WorkspaceState,
)
from cqa.backend.requests import AppealCreate, ReviewRequest
from cqa.backend.schemas import ChecklistCreate, DatasetEnvelope, EvaluationCreate, Schema
from cqa.backend.services.appeal_service import create_appeal, final_result, review_appeal
from cqa.backend.services.checklist_service import create_checklist
from cqa.backend.services.dataset_importer import Conflict, fetch_organizer, import_dataset
from cqa.backend.services.evaluation_jobs import create_job, inputs
from cqa.infra.orchestrator.pipeline import Finding
from cqa.normalization import NORMALIZATION_VERSION, normalize_messages
from cqa.service import EvaluationRequest
from cqa.service import Message as LegacyMessage
from cqa.workspace import default_checklist


class CompatibleEvaluationRequest(EvaluationRequest):
    # Optional explicit selection for the frontend owner's gradual endpoint migration.
    checklist_id: str | None = Field(default=None, min_length=1, max_length=100)


class WorkspaceRequest(Schema):
    revision: int = Field(ge=0)
    data: dict


def ui_messages(conversation, saved=None):
    saved = saved or []
    return [
        {
            "id": saved[i].get("id", f"m{i + 1}") if i < len(saved) else f"m{i + 1}",
            "role": m.speaker,
            "time": m.timestamp_original,
            "text": m.text,
        }
        for i, m in enumerate(conversation.messages)
    ]


def evaluation_view(session, row, messages=None, *, reviewed=False, cached=False):
    conversation, checklist = inputs(
        session, row.conversation_id, row.checklist_id, row.checklist_version
    )
    messages = ui_messages(conversation, messages)
    ids = {m.message_id: ui["id"] for m, ui in zip(conversation.messages, messages, strict=True)}
    result = final_result(session, row) if reviewed else row.result_json
    original = {
        r["criterionId"]: r for r in result["metadata"].get("analysis", {}).get("results", [])
    }
    findings = []
    for f in result["findings"]:
        extra = original.get(f["criterion_id"], {})
        if extra.get("answer") != f["answer"] or extra.get("reason") != f["explanation"]:
            extra = {}  # A human replacement must not inherit stale model evidence/review notes.
        refs = f["message_ids"] or (
            [] if extra.get("evidenceBasis") == "absence" else f["checked_message_ids"]
        )
        primary = extra.get("evidenceId")
        primary = primary if primary in f["message_ids"] else (refs[0] if refs else "")
        findings.append(
            {
                **extra,
                "criterionId": f["criterion_id"],
                "answer": f["answer"],
                "reason": f["explanation"],
                "evidenceId": ids[primary] if primary else "",
                "quote": extra.get("quote", "")
                if extra.get("evidenceId") in f["message_ids"]
                else "",
                "checkedMessageIds": [ids[mid] for mid in f["checked_message_ids"]],
                "evidence": [
                    {**e, "messageId": ids[e["messageId"]]}
                    for e in extra.get("evidence", [])
                    if e["messageId"] in f["message_ids"]
                ],
                "confidence": extra.get("confidence")
                if extra.get("answer") == f["answer"]
                else None,
            }
        )
    alias = session.scalar(
        select(WorkspaceChecklist).where(
            WorkspaceChecklist.checklist_id == row.checklist_id,
            WorkspaceChecklist.checklist_version == row.checklist_version,
        )
    )
    calls = result["metadata"].get("calls", [])
    usage = [call.get("usage", {}) for call in calls]
    return {
        "evaluationId": row.evaluation_id,
        "jobId": row.job_id,
        "conversation_id": row.conversation_id,
        "createdAt": row.created_at,
        "model": row.model_name,
        "is_mock": row.is_mock,
        "inputHash": session.get(EvaluationJob, row.job_id).cache_key,
        "checklistVersion": alias.ui_version if alias else row.checklist_version,
        "foundationChecklistId": row.checklist_id,
        "foundationChecklistVersion": row.checklist_version,
        "criteriaSnapshot": [c.model_dump(mode="json") for c in checklist.criteria],
        "summary": result["metadata"].get("summary", result["metadata"].get("notice", "")),
        "results": findings,
        "messages": messages,
        "requests": [
            {
                **r,
                "messageId": ids[r["messageId"]],
                "operatorMessageIds": [ids[mid] for mid in r["operatorMessageIds"]],
            }
            for r in result["metadata"].get("analysis", {}).get("requests", [])
        ],
        "reviewRecommended": any(f.get("reviewRecommended", False) for f in findings),
        "scoreProvisional": any(f.get("reviewRecommended", False) for f in findings),
        "score": result["score"],
        "critical": result["critical"],
        "tokens": sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
        if any("input_tokens" in u or "output_tokens" in u for u in usage)
        else None,
        "passes": len(calls),
        "metadata": result["metadata"],
        "cached": cached,
        "reviewRevision": row.review_revision,
    }


def ensure_checklist(db, session, criteria, ui_version):
    # Alias offline UI revisions to immutable canonical versions without inventing missing versions.
    request = ChecklistCreate(checklist_id="official", criteria=criteria)
    values = [c.model_dump(mode="json") for c in request.criteria]
    alias = session.get(WorkspaceChecklist, ui_version)
    if alias:
        row = session.get(Checklist, (alias.checklist_id, alias.checklist_version))
        if row.criteria != values:
            raise Conflict("Checklist version has different criteria; reload workspace")
        return row
    newest_alias = session.scalar(select(func.max(WorkspaceChecklist.ui_version))) or 0
    if ui_version <= newest_alias:
        raise Conflict("Stale checklist version; reload workspace")
    latest = session.scalar(
        select(Checklist)
        .where(Checklist.checklist_id == "official")
        .order_by(Checklist.version.desc())
        .limit(1)
    )
    already_mapped = (
        latest is not None
        and session.scalar(
            select(WorkspaceChecklist.ui_version)
            .where(
                WorkspaceChecklist.checklist_id == latest.checklist_id,
                WorkspaceChecklist.checklist_version == latest.version,
            )
            .limit(1)
        )
        is not None
    )
    if latest is None or latest.criteria != values or already_mapped:
        row = create_checklist(
            db,
            request.model_copy(update={"base_version": latest.version if latest else None}),
            session=session,
        )
    else:
        row = latest
    session.add(
        WorkspaceChecklist(
            ui_version=ui_version, checklist_id=row.checklist_id, checklist_version=row.version
        )
    )
    session.flush()
    return row


def import_dialog(db, session, dialog):
    messages = [LegacyMessage.model_validate(m) for m in dialog["messages"]]
    if not 1 <= len(messages) <= 500 or len({m.id for m in messages}) != len(messages):
        raise ValueError("Invalid message identifiers")
    if dialog["channel"] not in ("chat", "call"):
        raise ValueError("Invalid channel")
    cid = dialog["id"]
    existing = session.get(Conversation, cid)
    if existing:
        conversation, _ = inputs(session, cid, "official", 1)
        normalized, _ = normalize_messages(messages)
        supplied = [(m.role, m.time, m.text) for m in normalized]
        expected = [(m.speaker, m.timestamp_original, m.text) for m in conversation.messages]
        if (
            supplied != expected
            or dialog["language"] != conversation.language
            or dialog["channel"] != ("call" if conversation.channel == "voice call" else "chat")
            or dialog.get("audio_url") != conversation.audio_url
        ):
            raise Conflict("Conversation differs from immutable imported source")
        return
    record = {
        "conversation_id": cid,
        "language": dialog["language"],
        "channel": "voice call" if dialog["channel"] == "call" else "agent chat",
        "transcript": [
            {"speaker": m["role"], "timestamp": m["time"], "text": m["text"]}
            for m in dialog["messages"]
        ],
    }
    if dialog.get("audio_url"):
        record["audio_url"] = dialog["audio_url"]
    envelope = DatasetEnvelope.model_validate(
        {
            "isSuccess": True,
            "data": {"dataset_group_id": "workspace", "total_records": 1, "records": [record]},
        }
    )
    import_dataset(db, envelope, session=session)


def selected_evaluation(session, dialog):
    evaluation_id = dialog.get("evaluationId")
    row = (
        session.get(Evaluation, evaluation_id)
        if evaluation_id
        else session.scalar(
            select(Evaluation)
            .where(Evaluation.conversation_id == dialog["id"])
            .order_by(Evaluation.created_at.desc())
            .limit(1)
        )
    )
    if evaluation_id and (row is None or row.conversation_id != dialog["id"]):
        raise Conflict("Unknown evaluation for this conversation; reload history")
    return row


def sync_appeal(db, pipeline, session, value, dialogs):
    dialog = dialogs[value["dialogId"]]
    if not session.get(Conversation, dialog["id"]):
        return  # Deliberately synthetic frontend examples remain presentation-only.
    mapping = session.get(WorkspaceAppeal, value["id"])
    appeal = session.get(Appeal, mapping.appeal_id) if mapping else session.get(Appeal, value["id"])
    if appeal is None:
        row = selected_evaluation(session, dialog)
        if row is None:
            raise Conflict("Evaluate the conversation before appealing")
        appeal = create_appeal(
            db,
            AppealCreate(
                evaluation_id=row.evaluation_id,
                criterion_id=value["criterionId"],
                comment=value["comment"],
            ),
            session=session,
        )
        session.add(WorkspaceAppeal(ui_id=value["id"], appeal_id=appeal.appeal_id))
    row = session.get(Evaluation, appeal.evaluation_id)
    if (
        row.conversation_id != dialog["id"]
        or appeal.criterion_id != value["criterionId"]
        or appeal.comment != value["comment"]
    ):
        raise Conflict("Appeal source cannot be changed")
    if value["status"] == "resolved":
        reason = value["decision"]
        if appeal.status == "reviewed":
            final = session.scalar(
                select(ReviewHistory).where(ReviewHistory.appeal_id == appeal.appeal_id)
            ).final_result
            answer = next(
                f["answer"] for f in final["findings"] if f["criterion_id"] == appeal.criterion_id
            )
            if reason != appeal.reviewer_reason or value["newAnswer"] != answer:
                raise Conflict("Closed appeal cannot be rewritten")
            return
        conversation, _ = inputs(
            session, row.conversation_id, row.checklist_id, row.checklist_version
        )
        refs = {
            m["id"]: source.message_id
            for m, source in zip(dialog["messages"], conversation.messages, strict=True)
        }
        evidence = refs.get(value.get("evidenceId"))
        replacement = Finding(
            criterion_id=appeal.criterion_id,
            answer=value["newAnswer"],
            explanation=reason,
            message_ids=[evidence] if evidence else [],
            checked_message_ids=[m.message_id for m in conversation.messages],
            na_reason=reason if value["newAnswer"] == "N/A" else None,
        )
        review_appeal(
            db,
            pipeline,
            appeal.appeal_id,
            ReviewRequest(
                decision="accepted",
                reason=reason,
                base_revision=row.review_revision,
                replacement=replacement,
            ),
            session=session,
        )
        session.flush()
    elif value["status"] != "open" or appeal.status != "open":
        raise Conflict("Stale or invalid appeal status; reload workspace")


def workspace_view(db):
    with db.sessions() as session:
        state = session.get(WorkspaceState, 1)
        data = deepcopy(state.body) if state else {}
        rows = session.scalars(
            select(Conversation).order_by(Conversation.imported_at, Conversation.conversation_id)
        ).all()
        if not state and not rows:
            return {"revision": 0, "data": None}
        saved = {d["id"]: d for d in data.get("dialogs", [])}
        dialogs = []
        for row in rows:
            conversation, _ = inputs(session, row.conversation_id, "official", 1)
            extra = saved.pop(row.conversation_id, {})
            messages = ui_messages(conversation, extra.get("messages"))
            dialog = {
                "customer": "Клиент",
                "initials": "К",
                "agent": "Оператор",
                "topic": "Импортированный диалог",
                "date": "Импорт",
                "duration": "—",
                **extra,
                "id": row.conversation_id,
                "language": row.language,
                "channel": "call" if row.channel == "voice call" else "chat",
                "audio_url": row.audio_url,
                "messages": messages,
                "source": "import",
                "status": "pending",
                "score": None,
                "critical": False,
                "results": [],
            }
            evaluation = selected_evaluation(session, dialog)
            if evaluation:
                original = evaluation_view(session, evaluation, messages)
                dialog.update(
                    evaluation_view(session, evaluation, messages, reviewed=True),
                    status="done",
                    source="mock" if evaluation.is_mock else "ollama",
                    originalResults=original["results"],
                    originalScore=original["score"],
                )
            dialogs.append(dialog)
        data["dialogs"] = [*dialogs, *saved.values()]
        latest = session.scalar(
            select(Checklist)
            .where(Checklist.checklist_id == "official")
            .order_by(Checklist.version.desc())
            .limit(1)
        )
        alias = (
            session.scalar(
                select(WorkspaceChecklist)
                .where(
                    WorkspaceChecklist.checklist_id == "official",
                    WorkspaceChecklist.checklist_version == latest.version,
                )
                .order_by(WorkspaceChecklist.ui_version.desc())
                .limit(1)
            )
            if latest
            else None
        )
        max_ui = session.scalar(select(func.max(WorkspaceChecklist.ui_version))) or 0
        data["criteria"] = latest.criteria if latest else default_checklist()
        data["version"] = (
            alias.ui_version if alias else max(max_ui + 1, latest.version if latest else 1)
        )
        appeals = {a["id"]: a for a in data.get("appeals", [])}
        mappings = {m.appeal_id: m.ui_id for m in session.scalars(select(WorkspaceAppeal))}
        for appeal in session.scalars(select(Appeal).order_by(Appeal.created_at)):
            row = session.get(Evaluation, appeal.evaluation_id)
            original = next(
                f for f in row.result_json["findings"] if f["criterion_id"] == appeal.criterion_id
            )
            review = session.scalar(
                select(ReviewHistory).where(ReviewHistory.appeal_id == appeal.appeal_id)
            )
            current = next(
                f
                for f in (review.final_result if review else final_result(session, row))["findings"]
                if f["criterion_id"] == appeal.criterion_id
            )
            key = mappings.get(appeal.appeal_id, appeal.appeal_id)
            _, checklist = inputs(
                session, row.conversation_id, row.checklist_id, row.checklist_version
            )
            criterion = next(c for c in checklist.criteria if c.id == appeal.criterion_id)
            appeals[key] = {
                **appeals.get(key, {}),
                "id": key,
                "evaluationId": row.evaluation_id,
                "dialogId": row.conversation_id,
                "criterionId": appeal.criterion_id,
                "criterion": criterion.model_dump(mode="json"),
                "title": criterion.title,
                "originalAnswer": original["answer"],
                "originalReason": original["explanation"],
                "comment": appeal.comment,
                "status": "open" if appeal.status == "open" else "resolved",
                "date": appeal.created_at,
                "newAnswer": current["answer"],
                "decision": appeal.reviewer_reason,
            }
        data["appeals"] = list(appeals.values())
        return {"revision": state.revision if state else 0, "data": data}


def save_workspace(db, pipeline, request):
    if len(json.dumps(request.data, ensure_ascii=False).encode()) > 10_000_000:
        raise HTTPException(413, "Workspace exceeds 10 MB")
    data = deepcopy(request.data)
    try:
        with db.sessions.begin() as session:
            # Serialize a whole compatibility save, including imports/checklists/reviews.
            if db.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            state = session.get(WorkspaceState, 1)
            if request.revision != (state.revision if state else 0):
                raise Conflict("Workspace changed; export local edits and reload")
            if "criteria" in data:
                if type(data["version"]) is not int or data["version"] < 1:
                    raise ValueError("Invalid version")
                ensure_checklist(db, session, data["criteria"], data["version"])
            dialogs = data.get("dialogs", [])
            if len(dialogs) > 1000 or len({d["id"] for d in dialogs}) != len(dialogs):
                raise ValueError("Invalid dialogs")
            for dialog in dialogs:
                if dialog.get("source") in (
                    "import",
                    "organizer",
                    "ai",
                    "ollama",
                    "mock",
                ) or session.get(Conversation, dialog["id"]):
                    import_dialog(db, session, dialog)
                    selected_evaluation(session, dialog)
            by_id = {d["id"]: d for d in dialogs}
            for appeal in data.get("appeals", []):
                if appeal.get("dialogId") in by_id:
                    sync_appeal(db, pipeline, session, appeal, by_id)
            # Real transcripts, findings and scores exist only in canonical tables.
            for i, dialog in enumerate(dialogs):
                if session.get(Conversation, dialog["id"]):
                    dialogs[i] = {
                        k: v
                        for k, v in dialog.items()
                        if k
                        in (
                            "id",
                            "customer",
                            "initials",
                            "agent",
                            "topic",
                            "date",
                            "duration",
                            "evaluationId",
                        )
                    }
                    dialogs[i]["messages"] = [{"id": m["id"]} for m in dialog["messages"]]
            data.pop("criteria", None)
            data.pop("version", None)
            revision = request.revision + 1
            if state:
                state.revision, state.body = revision, data
            else:
                session.add(WorkspaceState(workspace_id=1, revision=revision, body=data))
        return {"revision": revision}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid workspace structure") from exc


def install_compat(app, db, pipeline, settings, transport=None):
    @app.get("/api/workspace")
    def get_workspace():
        return workspace_view(db)

    @app.put("/api/workspace")
    def put_workspace(request: WorkspaceRequest):
        return save_workspace(db, pipeline, request)

    @app.get("/api/history/{conversation_id:path}")
    def history(conversation_id: str):
        with db.sessions() as session:
            return [
                evaluation_view(session, row)
                for row in session.scalars(
                    select(Evaluation)
                    .where(Evaluation.conversation_id == conversation_id)
                    .order_by(Evaluation.created_at.desc())
                )
            ]

    @app.get("/api/organizer")
    async def organizer(group_id: str = "DEV"):
        envelope = await fetch_organizer(settings, group_id, transport)
        import_dataset(db, envelope)
        return envelope.model_dump(mode="json")

    @app.get("/api/workspace-evaluations/{job_id}")
    def workspace_evaluation(job_id: str):
        """Poll durable work without keeping a serverless proxy request open."""
        with db.sessions() as session:
            job = session.get(EvaluationJob, job_id)
            if job is None:
                raise LookupError()
            view = {"jobId": job.job_id, "status": job.status}
            if job.status == "failed":
                # Workers persist only redacted, actionable error messages.
                view["error"] = job.error_message or "Evaluation failed"
            elif job.status == "completed":
                row = session.scalar(select(Evaluation).where(Evaluation.job_id == job_id))
                if row is None:
                    raise HTTPException(503, "Evaluation result is temporarily unavailable")
                view["result"] = evaluation_view(session, row, reviewed=True)
            return view

    @app.post("/api/evaluate")
    async def evaluate(request: CompatibleEvaluationRequest, async_job: bool = False):
        with db.sessions.begin() as session:
            if db.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if request.checklist_id:
                checklist = session.get(Checklist, (request.checklist_id, request.version))
                if checklist is None:
                    raise LookupError()
                if checklist.criteria != [c.model_dump(mode="json") for c in request.criteria]:
                    raise Conflict("Inline criteria differ from saved checklist version")
            else:
                checklist = ensure_checklist(db, session, request.criteria, request.version)
            existing = session.get(Conversation, request.conversation_id)
            dialog = {
                "id": request.conversation_id,
                "language": request.language,
                "channel": "call" if existing and existing.channel == "voice call" else "chat",
                "audio_url": existing.audio_url if existing else None,
                "messages": [m.model_dump() for m in request.messages],
            }
            import_dialog(db, session, dialog)
            checklist_id, version = checklist.checklist_id, checklist.version
        job = create_job(
            db,
            pipeline,
            settings,
            EvaluationCreate(
                conversation_id=request.conversation_id,
                checklist_id=checklist_id,
                checklist_version=version,
                force=request.force,
                retry_failed=request.force,
            ),
        )
        cached = job.status == "completed"
        if async_job:
            return JSONResponse(
                status_code=202,
                content={"jobId": job.job_id, "status": job.status, "cached": cached},
                headers={"Location": f"/api/workspace-evaluations/{job.job_id}"},
            )
        # Only the managed worker executes jobs. Disconnect/timeout does not cancel durable work.
        try:
            async with asyncio.timeout(settings.timeout + 5):
                while True:
                    with db.sessions() as session:
                        current = session.get(EvaluationJob, job.job_id)
                        if current.status == "failed":
                            raise HTTPException(502, current.error_message)
                        if current.status == "completed":
                            row = session.scalar(
                                select(Evaluation).where(Evaluation.job_id == job.job_id)
                            )
                            result = evaluation_view(
                                session, row, dialog["messages"], reviewed=True, cached=cached
                            )
                            result["checklistVersion"] = request.version
                            _, changes = normalize_messages(request.messages)
                            if changes:
                                result["normalization"] = {
                                    "version": NORMALIZATION_VERSION,
                                    "changes": changes,
                                }
                            return result
                    await asyncio.sleep(0.05)
        except TimeoutError as exc:
            raise HTTPException(
                504, {"message": "Job still queued; poll job endpoint", "job_id": job.job_id}
            ) from exc

    static = Path(settings.frontend_dir).resolve()
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
