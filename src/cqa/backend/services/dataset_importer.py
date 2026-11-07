"""Validated atomic imports. No transcript or signed URL is logged."""

import hashlib

from cqa.backend.models import Conversation, Message
from cqa.backend.schemas import DatasetEnvelope, ImportResult


class Conflict(ValueError):
    pass


def message_id(conversation_id, index):
    return "msg_" + hashlib.sha256(f"{conversation_id}\0{index}".encode()).hexdigest()


def import_dataset(db, envelope: DatasetEnvelope):
    dataset = envelope.data
    imported = 0
    with db.sessions.begin() as session:
        for record in dataset.records:
            payload = record.model_dump(mode="json", exclude_unset=True)
            existing = session.get(Conversation, record.conversation_id)
            if existing:
                if (
                    existing.original_payload != payload
                    or existing.dataset_group_id != dataset.dataset_group_id
                ):
                    raise Conflict("Conversation ID already exists with different source data")
                continue
            session.add(
                Conversation(
                    conversation_id=record.conversation_id,
                    dataset_group_id=dataset.dataset_group_id,
                    channel=record.channel,
                    language=record.language,
                    audio_url=record.audio_url,
                    original_payload=payload,
                )
            )
            session.flush()
            for index, message in enumerate(record.transcript):
                session.add(
                    Message(
                        message_id=message_id(record.conversation_id, index),
                        conversation_id=record.conversation_id,
                        message_index=index,
                        speaker=message.speaker,
                        timestamp_original=message.timestamp,
                        text=message.text,
                    )
                )
            imported += 1
    return ImportResult(
        dataset_group_id=dataset.dataset_group_id,
        total_records=dataset.total_records,
        imported=imported,
        skipped=dataset.total_records - imported,
    )
