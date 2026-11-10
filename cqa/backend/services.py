"""Import and DTO helpers. Never log signed request URLs or transcript text."""
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from cqa.backend.models import Conversation, Message

VALID_ROLES = {"client", "operator", "bot", "system"}
VALID_CHANNELS = {"agent chat", "voice call"}
VALID_LANGUAGES = {"RU", "KZ", "EN"}


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def parse_dataset(payload: dict, expected_group: str | None = None):
    if not isinstance(payload, dict) or payload.get("isSuccess") is not True or payload.get("error") not in (None, ""):
        raise HTTPException(422, "Dataset response is not successful")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise HTTPException(422, "data.records must be an array")
    group = data.get("dataset_group_id")
    if not isinstance(group, str) or not group or (expected_group and group != expected_group):
        raise HTTPException(422, "Dataset group mismatch or missing group")
    records = data["records"]
    if type(data.get("total_records")) is not int or data["total_records"] != len(records):
        raise HTTPException(422, "total_records does not match records length")
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise HTTPException(422, "Each record must be an object")
        cid = record.get("conversation_id")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise HTTPException(422, "Missing or duplicate conversation_id")
        seen.add(cid)
        if record.get("channel") not in VALID_CHANNELS or record.get("language") not in VALID_LANGUAGES:
            raise HTTPException(422, "Invalid channel or language")
        if not isinstance(record.get("transcript"), list):
            raise HTTPException(422, "transcript must be an array")
        audio_url = record.get("audio_url")
        if audio_url is not None and not isinstance(audio_url, str):
            raise HTTPException(422, "audio_url must be a string or null")
        for item in record["transcript"]:
            if (not isinstance(item, dict) or item.get("speaker") not in VALID_ROLES
                    or not isinstance(item.get("timestamp"), str)
                    or not isinstance(item.get("text"), str)):
                raise HTTPException(422, "Invalid transcript message")
    return group, records


def import_dataset(db, payload: dict, expected_group: str | None = None):
    group, records = parse_dataset(payload, expected_group)
    counts = {"total": len(records), "created": 0, "updated": 0, "unchanged": 0, "messages": 0}
    try:
        for record in records:
            cid = record["conversation_id"]
            existing = db.scalar(select(Conversation).where(Conversation.conversation_id == cid, Conversation.dataset_group_id == group))
            if existing and existing.original_payload == record:
                counts["unchanged"] += 1
                counts["messages"] += len(record["transcript"])
                continue
            if existing:
                conv = existing
                db.query(Message).filter(Message.conversation_ref == conv.id).delete(synchronize_session=False)
                counts["updated"] += 1
            else:
                conv = Conversation(conversation_id=cid, dataset_group_id=group, channel=record["channel"], language=record["language"], original_payload=record)
                db.add(conv)
                db.flush()
                counts["created"] += 1
            conv.channel = record["channel"]
            conv.language = record["language"]
            conv.audio_url = record.get("audio_url")
            conv.original_payload = record
            for i, msg in enumerate(record["transcript"]):
                mid = hashlib.sha256(f"{group}\x00{cid}\x00{i}".encode()).hexdigest()[:32]
                db.add(Message(message_id=mid, conversation_ref=conv.id, message_index=i, speaker=msg["speaker"], timestamp_original=msg["timestamp"], text=msg["text"]))
            counts["messages"] += len(record["transcript"])
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"dataset_group_id": group, **counts}


def conversation_out(conv: Conversation, include_messages=False):
    result = {"conversation_id": conv.conversation_id, "dataset_group_id": conv.dataset_group_id,
              "channel": conv.channel, "language": conv.language, "audio_url": conv.audio_url,
              "imported_at": conv.imported_at.isoformat()}
    if include_messages:
        result["messages"] = [{"message_id": m.message_id, "message_index": m.message_index,
                               "speaker": m.speaker, "timestamp_original": m.timestamp_original,
                               "text": m.text} for m in conv.messages]
        result["original_payload"] = conv.original_payload
    return result


async def download_dataset(url: str):
    if not url:
        raise HTTPException(503, "Dataset endpoint is not configured")
    timeout = httpx.Timeout(15.0, connect=5.0)
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.get(url)
            if response.status_code in (401, 403):
                raise HTTPException(502, "Dataset provider rejected authorization")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise HTTPException(502, "Dataset provider temporarily unavailable")
            if response.status_code != 200:
                raise HTTPException(502, "Dataset provider returned unexpected HTTP status")
            try:
                return response.json()
            except ValueError:
                raise HTTPException(502, "Invalid JSON from dataset provider") from None
        except httpx.HTTPError:
            if attempt == 2:
                raise HTTPException(502, "Dataset provider network error") from None
            await asyncio.sleep(0.25 * 2**attempt)
    raise HTTPException(502, "Dataset provider unavailable")


def load_dataset_file(path: str):
    try:
        file = Path(path)
        if file.stat().st_size > 30_000_000:
            raise HTTPException(413, "Dataset file too large")
        return json.loads(file.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, IsADirectoryError):
        raise HTTPException(404, "Configured dataset file not found") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(422, "Dataset file is not valid UTF-8 JSON") from None
