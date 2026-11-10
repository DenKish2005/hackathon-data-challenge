"""DB-backed single-worker orchestration and explicit evaluator integration seam."""
import asyncio
import uuid
from contextlib import suppress
from sqlalchemy import select

from cqa.backend.models import (Checklist, Conversation, Evaluation, EvaluationJob, Message, utcnow)
from cqa.backend.services import conversation_out
from cqa.infra.llm import cache_key


class MockEvaluator:
    """A synthetic protocol test, not a judgement of any operator."""
    name = "mock-evaluator"
    model_name = "mock"
    prompt_version = "mock-v1"

    async def evaluate_conversation(self, conversation: dict, checklist: dict) -> dict:
        answers = []
        for c in checklist["criteria"]:
            answer = 0 if c["type"] == "scale" else "Нет"
            answers.append({"criterion_id": str(c["id"]), "answer": answer,
                            "reason": "Synthetic placeholder only; no conversation evaluation performed.",
                            "evidence_message_ids": [], "checked_message_ids": [], "na_reason": None})
        return {"criteria": answers, "total_score": None, "critical_error": None,
                "is_mock": True, "is_evaluated": False,
                "metadata": {"evaluator": self.name, "model": self.model_name, "prompt_version": self.prompt_version}}


class PipelineWorker:
    """One worker per application process; pending jobs survive process restarts."""
    def __init__(self, session_factory, evaluator=None, poll_seconds=0.25, scorer=None):
        self.sessions = session_factory
        self.evaluator = evaluator or MockEvaluator()
        self.scorer = scorer  # Scoring Engine owned by team member 2.
        self.poll_seconds = poll_seconds
        self.task = None

    async def start(self):
        with self.sessions() as db:
            # Single-process recovery. In multi-worker production use atomic claims/leases.
            for job in db.scalars(select(EvaluationJob).where(EvaluationJob.status == "running")):
                job.status = "pending"
                job.error_message = "Recovered after interrupted worker"
            db.commit()
        self.task = asyncio.create_task(self.run_forever())

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def run_forever(self):
        while True:
            try:
                await self.process_one()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Individual job failures are recorded; worker remains alive.
                pass
            await asyncio.sleep(self.poll_seconds)

    async def process_one(self):
        with self.sessions() as db:
            job = db.scalar(select(EvaluationJob).where(EvaluationJob.status == "pending").order_by(EvaluationJob.created_at, EvaluationJob.job_id).limit(1))
            if job is None:
                return False
            job.status = "running"
            job.updated_at = utcnow()
            db.commit()
            job_id = job.job_id
        try:
            with self.sessions() as db:
                job = db.get(EvaluationJob, job_id)
                conv = db.get(Conversation, job.conversation_ref)
                checklist = db.get(Checklist, job.checklist_ref)
                # Make a complete immutable snapshot before calling an external evaluator.
                messages = db.scalars(select(Message).where(Message.conversation_ref == conv.id).order_by(Message.message_index)).all()
                data = conversation_out(conv)
                data["messages"] = [{"message_id": m.message_id, "message_index": m.message_index,
                                     "speaker": m.speaker, "timestamp_original": m.timestamp_original, "text": m.text} for m in messages]
                checklist_data = {"checklist_id": checklist.checklist_id, "version": checklist.version,
                                  "criteria": checklist.criteria, "sections": checklist.sections}
            result = await self.evaluator.evaluate_conversation(data, checklist_data)
            if not isinstance(result, dict):
                raise ValueError("Evaluator returned non-object")
            if not result.get("is_mock") and self.scorer:
                result = await self.scorer.score(result, checklist_data)
            # Preserve input and official criterion snapshots in every stored evaluation.
            result["conversation_snapshot"] = data
            result["checklist_snapshot"] = checklist_data
            result["input_hash"] = cache_key(data, checklist_data["checklist_id"], checklist_data["version"], getattr(self.evaluator, "prompt_version", "unspecified"), getattr(self.evaluator, "model_name", "unspecified"))
            with self.sessions() as db:
                job = db.get(EvaluationJob, job_id)
                if not db.scalar(select(Evaluation).where(Evaluation.job_id == job_id)):
                    db.add(Evaluation(evaluation_id=str(uuid.uuid4()), conversation_ref=job.conversation_ref,
                                      job_id=job_id, checklist_id=job.checklist_id,
                                      checklist_version=job.checklist_version,
                                      evaluator_name=getattr(self.evaluator, "name", "external-evaluator"),
                                      model_name=getattr(self.evaluator, "model_name", "unspecified"),
                                      prompt_version=getattr(self.evaluator, "prompt_version", "unspecified"),
                                      result_json=result, is_mock=bool(result.get("is_mock", False))))
                job.status = "completed"
                job.error_message = None
                job.updated_at = utcnow()
                db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            with self.sessions() as db:
                job = db.get(EvaluationJob, job_id)
                job.status = "failed"
                job.error_message = "Evaluator failed; inspect private server diagnostics"
                job.updated_at = utcnow()
                db.commit()
        return True
