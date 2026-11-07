"""Dataset normalization and optimistic persistence shared by API and batch CLI."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from cqa.service import Criterion, EvaluationRequest


class WorkspaceConflict(ValueError):
    pass


def default_checklist():
    path = Path(__file__).with_name("checklist.json")
    return [Criterion.model_validate(c).model_dump() for c in json.loads(path.read_text())]


def read_workspace(store):
    with store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS workspace "
            "(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)"
        )
        row = db.execute("SELECT revision,body FROM workspace WHERE id=1").fetchone()
    return (
        {"revision": row[0], "data": json.loads(row[1])} if row else {"revision": 0, "data": None}
    )


def write_workspace(store, revision, data):
    body = json.dumps(data, ensure_ascii=False)
    if len(body.encode()) > 10_000_000:
        raise ValueError("Рабочее пространство превышает 10 МБ")
    read_workspace(store)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM workspace WHERE id=1").fetchone()
        current = row[0] if row else 0
        if current != revision:
            raise WorkspaceConflict(
                "Данные изменились. Экспортируйте изменения и обновите страницу."
            )
        db.execute("INSERT OR REPLACE INTO workspace VALUES (1,?,?)", (current + 1, body))
    return {"revision": current + 1}


def normalize_records(payload, criteria, version, existing=()):
    if isinstance(payload, dict) and payload.get("isSuccess") is False:
        raise ValueError("API организаторов сообщил об ошибке")
    if not isinstance(payload, (dict, list)):
        raise ValueError("Нужен JSON-объект или массив")
    container = payload.get("data", payload) if isinstance(payload, dict) else None
    records = (
        payload
        if isinstance(payload, list)
        else (container.get("records") if isinstance(container, dict) else None)
    )
    if not isinstance(records, list) or not records or len(records) > 1000:
        raise ValueError("Нужен массив из 1–1000 записей records")
    ids = {d["id"] for d in existing}
    dialogs = []
    for r in records:
        if not isinstance(r, dict):
            raise ValueError("Запись должна быть объектом")
        cid = r.get("conversation_id")
        if not isinstance(cid, str) or not cid.strip():
            raise ValueError("Нужен непустой conversation_id")
        if cid in ids:
            raise ValueError(f"Повторяющийся диалог: {cid}")
        if r.get("channel") not in ("agent chat", "voice call"):
            raise ValueError("Канал должен быть agent chat или voice call")
        audio = r.get("audio_url")
        if audio:
            if not isinstance(audio, str):
                raise ValueError("Ссылка на аудио должна быть строкой")
            try:
                audio_parts = urlsplit(audio)
                if (
                    audio_parts.scheme != "https"
                    or not audio_parts.hostname
                    or audio_parts.username is not None
                    or audio_parts.password is not None
                ):
                    raise ValueError("Для аудио требуется корректная HTTPS-ссылка")
                _ = audio_parts.port
            except ValueError as exc:
                raise ValueError("Для аудио требуется корректная HTTPS-ссылка") from exc
        transcript = r.get("transcript")
        if (
            not isinstance(transcript, list)
            or not transcript
            or not all(isinstance(m, dict) for m in transcript)
        ):
            raise ValueError(
                "Нужен непустой transcript. Для телефонного разговора нужна расшифровка."
            )
        request = EvaluationRequest(
            conversation_id=cid,
            language=r.get("language"),
            criteria=criteria,
            version=version,
            messages=[
                {
                    "id": f"m{i + 1}",
                    "role": m.get("speaker"),
                    "time": m.get("timestamp"),
                    "text": m.get("text"),
                }
                for i, m in enumerate(transcript)
            ],
        )
        ids.add(cid)
        dialogs.append(
            {
                "id": cid,
                "customer": "Клиент",
                "initials": "К",
                "agent": "Оператор",
                "topic": "Импортированный диалог",
                "language": request.language,
                "channel": "call" if r["channel"] == "voice call" else "chat",
                "date": "Импорт",
                "duration": "—",
                "status": "pending",
                "score": None,
                "critical": False,
                "results": [],
                "source": "import",
                "messages": [m.model_dump() for m in request.messages],
                "audio_url": audio or None,
            }
        )
    return dialogs
