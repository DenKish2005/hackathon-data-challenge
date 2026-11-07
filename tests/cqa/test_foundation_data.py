import copy

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from cqa.backend.models import Checklist, Conversation, Message
from cqa.backend.schemas import ChecklistCreate, DatasetEnvelope
from cqa.backend.services.checklist_service import create_checklist
from cqa.backend.services.dataset_importer import Conflict, import_dataset
from cqa.workspace import default_checklist


def dataset_payload():
    """Synthetic shape/count fixture; never represented as the organizer DEV data."""
    records = []
    for i in range(65):
        call = i >= 60
        records.append(
            {
                "conversation_id": f"synthetic-{i}",
                "channel": "voice call" if call else "agent chat",
                "language": "RU" if i < 35 else "KZ" if i < 50 else "EN",
                "transcript": [
                    {
                        "speaker": speaker,
                        "text": f"Synthetic message {n}",
                        "timestamp": f"2026-01-01T12:00:0{n}.123456+05:00" if call else f"00:0{n}",
                    }
                    for n, speaker in enumerate(("client", "bot", "operator", "system"))
                ],
                "audio_url": f"https://example.test/{i}.mp3" if call else None,
            }
        )
    return {
        "error": "",
        "isSuccess": True,
        "data": {"dataset_group_id": "DEV", "total_records": 65, "records": records},
    }


def test_import_preserves_records_and_is_atomic_idempotent(database):
    payload = dataset_payload()
    envelope = DatasetEnvelope.model_validate(payload)
    assert import_dataset(database, envelope).imported == 65
    assert import_dataset(database, envelope).skipped == 65
    with database.sessions() as session:
        conversations = session.scalars(select(Conversation)).all()
        assert len(conversations) == 65
        assert sum(c.channel == "agent chat" for c in conversations) == 60
        assert {
            lang: sum(c.language == lang for c in conversations) for lang in ("RU", "KZ", "EN")
        } == {"RU": 35, "KZ": 15, "EN": 15}
        messages = session.scalars(
            select(Message)
            .where(Message.conversation_id == "synthetic-64")
            .order_by(Message.message_index)
        ).all()
        stable_ids = [m.message_id for m in messages]
        assert len(set(stable_ids)) == 4
        assert [m.speaker for m in messages] == ["client", "bot", "operator", "system"]
        assert messages[0].timestamp_original == "2026-01-01T12:00:00.123456+05:00"
        assert session.get(Conversation, "synthetic-64").audio_url == "https://example.test/64.mp3"
        assert (
            session.get(Conversation, "synthetic-64").original_payload
            == payload["data"]["records"][64]
        )
    changed = copy.deepcopy(payload)
    changed["data"]["records"][0]["conversation_id"] = "new-record"
    changed["data"]["records"][1]["transcript"][0]["text"] = "changed"
    with pytest.raises(Conflict):
        import_dataset(database, DatasetEnvelope.model_validate(changed))
    with database.sessions() as session:
        assert session.get(Conversation, "new-record") is None
        assert stable_ids == [
            m.message_id
            for m in session.scalars(
                select(Message)
                .where(Message.conversation_id == "synthetic-64")
                .order_by(Message.message_index)
            )
        ]


@pytest.mark.parametrize(
    "change", ["count", "duplicate", "speaker", "timezone", "audio", "success"]
)
def test_invalid_dataset(change):
    data = dataset_payload()
    if change == "count":
        data["data"]["total_records"] = 64
    elif change == "duplicate":
        data["data"]["records"][1]["conversation_id"] = "synthetic-0"
    elif change == "speaker":
        data["data"]["records"][0]["transcript"][0]["speaker"] = "agent"
    elif change == "timezone":
        data["data"]["records"][-1]["transcript"][0]["timestamp"] = "2026-01-01T12:00:00"
    elif change == "audio":
        data["data"]["records"][-1]["audio_url"] = "javascript:alert(1)"
    else:
        data["isSuccess"] = False
    with pytest.raises(ValidationError):
        DatasetEnvelope.model_validate(data)


def test_append_only_checklists(database):
    criteria = default_checklist()
    first = create_checklist(database, ChecklistCreate(checklist_id="official", criteria=criteria))
    criteria[0]["weight"] = 11
    second = create_checklist(
        database, ChecklistCreate(checklist_id="official", base_version=1, criteria=criteria)
    )
    assert (first.version, second.version) == (1, 2)
    with database.sessions() as session:
        assert session.get(Checklist, ("official", 1)).criteria[0]["weight"] == 10
    with pytest.raises(Conflict):
        create_checklist(
            database, ChecklistCreate(checklist_id="official", base_version=1, criteria=criteria)
        )
    assert criteria[3]["scale"] == [0, 5, 10, 15, 20]
    assert criteria[5]["scale"] == [0, 4, 7, 10]
    assert sum(c["weight"] for c in default_checklist()) == 100


def test_real_dev_file_when_supplied(database):
    import json
    import os
    from pathlib import Path

    path = os.getenv("CQA_TEST_DEV_FILE")
    if not path:
        pytest.skip("Set CQA_TEST_DEV_FILE to a private local DEV JSON")
    payload = DatasetEnvelope.model_validate(json.loads(Path(path).read_text(encoding="utf-8-sig")))
    assert len(payload.data.records) == 65
    assert sum(len(r.transcript) for r in payload.data.records) == 1268
    assert sum(r.channel == "agent chat" for r in payload.data.records) == 60
    assert {
        lang: sum(r.language == lang for r in payload.data.records) for lang in ("RU", "KZ", "EN")
    } == {"RU": 35, "KZ": 15, "EN": 15}
    assert import_dataset(database, payload).imported == 65
