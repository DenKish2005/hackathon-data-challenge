"""Validated atomic imports. No transcript or signed URL is logged."""

import hashlib
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx

from cqa.backend.models import Conversation, Message
from cqa.backend.schemas import DatasetEnvelope, ImportResult
from cqa.infra.llm.base import ProviderError, request_json
from cqa.normalization import repair_mojibake


class Conflict(ValueError):
    pass


def message_id(conversation_id, index):
    return "msg_" + hashlib.sha256(f"{conversation_id}\0{index}".encode()).hexdigest()


async def fetch_organizer(settings, group_id, transport=None):
    url = settings.organizer_urls.get(group_id)
    if not url:
        raise LookupError("Dataset group is not configured on the server")
    parts = urlsplit(url)
    host = parts.hostname or ""
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or not (
            host == "environment.api.powerplatform.com"
            or host.endswith(".environment.api.powerplatform.com")
        )
    ):
        raise ProviderError("Organizer endpoint configuration is invalid")
    # The signed URL is used verbatim. Never rewrite group_id or follow redirects.
    async with httpx.AsyncClient(
        # Honor the managed environment's HTTPS proxy and trusted CA bundle.
        # Disabling this prevents real organizer imports on proxy-only networks.
        timeout=60, transport=transport, trust_env=True, follow_redirects=False
    ) as client:
        payload = await request_json(client, "GET", url)
    try:
        envelope = DatasetEnvelope.model_validate(payload)
        if envelope.data.dataset_group_id != group_id:
            raise ValueError("Unexpected dataset group")
        return envelope
    except ValueError as exc:
        raise ProviderError("Organizer returned an invalid dataset") from exc


def import_dataset(db, envelope: DatasetEnvelope, *, session=None):
    dataset = envelope.data
    imported = 0
    with nullcontext(session) if session is not None else db.sessions.begin() as session:
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
                        text=repair_mojibake(message.text),
                    )
                )
            imported += 1
    return ImportResult(
        dataset_group_id=dataset.dataset_group_id,
        total_records=dataset.total_records,
        imported=imported,
        skipped=dataset.total_records - imported,
    )
