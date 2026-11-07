"""One controlled worker pool per database. Database is the durable queue."""

import asyncio
import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select, update

from cqa.backend.models import Evaluation, EvaluationJob, now
from cqa.backend.services.evaluation_jobs import inputs, job_key

logger = logging.getLogger(__name__)


@contextmanager
def worker_lock(db):
    """Fail visibly if a second app tries to recover jobs in the same SQLite DB."""
    if (
        db.engine.dialect.name != "sqlite"
        or not db.engine.url.database
        or db.engine.url.database == ":memory:"
    ):
        raise ValueError(
            "Worker currently requires file SQLite; use an external queue for PostgreSQL"
        )
    path = Path(db.engine.url.database).resolve().with_suffix(".worker.lock")
    with path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if __import__("os").name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another CQA worker owns this database") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("Another CQA worker owns this database") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Worker:
    def __init__(self, db, pipeline, settings):
        self.db, self.pipeline, self.settings = db, pipeline, settings

    def recover(self):
        with self.db.sessions.begin() as session:
            for job in session.scalars(
                select(EvaluationJob).where(EvaluationJob.status == "running")
            ):
                job.status = "pending" if job.attempts < 3 else "failed"
                job.error_message = (
                    None if job.status == "pending" else "Restart attempt limit reached"
                )
                job.updated_at = now()

    def claim(self):
        with self.db.sessions.begin() as session:
            candidate = session.scalar(
                select(EvaluationJob.job_id)
                .where(EvaluationJob.status == "pending")
                .order_by(EvaluationJob.created_at)
                .limit(1)
            )
            if not candidate:
                return None
            changed = session.execute(
                update(EvaluationJob)
                .where(EvaluationJob.job_id == candidate, EvaluationJob.status == "pending")
                .values(status="running", updated_at=now(), attempts=EvaluationJob.attempts + 1)
            )
            return candidate if changed.rowcount == 1 else None

    async def process_one(self):
        job_id = self.claim()
        if not job_id:
            return False
        try:
            with self.db.sessions() as session:
                job = session.get(EvaluationJob, job_id)
                conversation, checklist = inputs(
                    session, job.conversation_id, job.checklist_id, job.checklist_version
                )
                if job.cache_key.split(":")[0] != job_key(
                    conversation, checklist, self.pipeline, self.settings
                ):
                    raise ValueError(
                        "Pipeline configuration changed; resubmit with current configuration"
                    )
            async with asyncio.timeout(self.settings.timeout):
                result = await self.pipeline.run(conversation, checklist)
            result["metadata"]["prompt_version"] = self.settings.prompt_version
            with self.db.sessions.begin() as session:
                job = session.get(EvaluationJob, job_id)
                session.add(
                    Evaluation(
                        job_id=job_id,
                        conversation_id=job.conversation_id,
                        checklist_id=job.checklist_id,
                        checklist_version=job.checklist_version,
                        evaluator_name=self.pipeline.evaluator.name,
                        model_name=self.pipeline.evaluator.model,
                        prompt_version=self.settings.prompt_version,
                        is_mock=self.pipeline.evaluator.is_mock,
                        result_json=result,
                    )
                )
                job.status, job.error_message, job.updated_at = "completed", None, now()
        except asyncio.CancelledError:
            # Leave RUNNING durable for controlled recovery; no result committed yet.
            raise
        except Exception as exc:
            # Never persist exception text: providers can embed credentials or transcripts.
            error = "Evaluation timed out" if isinstance(exc, TimeoutError) else "Evaluation failed"
            with self.db.sessions.begin() as session:
                job = session.get(EvaluationJob, job_id)
                job.status, job.error_message, job.updated_at = "failed", error, now()
            logger.warning("evaluation job=%s failed type=%s", job_id, type(exc).__name__)
        return True

    async def run(self):
        while True:
            if not await self.process_one():
                await asyncio.sleep(0.1)
