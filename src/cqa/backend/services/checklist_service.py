"""Append-only checklist versions with optimistic concurrency control."""

from contextlib import nullcontext

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cqa.backend.models import Checklist
from cqa.backend.services.dataset_importer import Conflict


def seed_checklist(db):
    from cqa.backend.schemas import ChecklistCreate
    from cqa.workspace import default_checklist

    with db.sessions() as session:
        seeded = session.get(Checklist, ("official", 1)) is not None
    if not seeded:
        try:
            create_checklist(
                db, ChecklistCreate(checklist_id="official", criteria=default_checklist())
            )
        except Conflict:
            pass


def create_checklist(db, request, *, session=None):
    try:
        with nullcontext(session) if session is not None else db.sessions.begin() as session:
            latest = session.scalar(
                select(func.max(Checklist.version)).where(
                    Checklist.checklist_id == request.checklist_id
                )
            )
            if latest != request.base_version:
                raise Conflict("Use the latest base_version to create a new checklist version")
            checklist = Checklist(
                checklist_id=request.checklist_id,
                version=(latest or 0) + 1,
                criteria=[c.model_dump(mode="json") for c in request.criteria],
                sections=request.sections,
            )
            session.add(checklist)
            session.flush()
        return checklist
    except IntegrityError as exc:
        raise Conflict("Checklist version was created concurrently; reload and retry") from exc
