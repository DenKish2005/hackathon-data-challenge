import json
import subprocess
import sys

import pytest

from cqa.service import Store
from cqa.workspace import default_checklist, normalize_records, read_workspace, write_workspace


def record(cid="unseen"):
    return {
        "conversation_id": cid,
        "language": "EN",
        "channel": "agent chat",
        "transcript": [{"speaker": "operator", "timestamp": "00:01", "text": "Hello, I'm Alex."}],
    }


def test_import_normalization_and_duplicates():
    criteria = default_checklist()
    dialogs = normalize_records({"data": {"records": [record()]}}, criteria, 1)
    assert dialogs[0]["messages"][0]["time"] == "00:01"
    assert dialogs[0]["status"] == "pending"
    assert dialogs[0]["score"] is None
    with pytest.raises(ValueError):
        normalize_records([record()], criteria, 1, dialogs)
    with pytest.raises(ValueError):
        normalize_records([record(), record()], criteria, 1)


def test_phone_call_keeps_original_transcript_audio_and_pending_state():
    call = {
        **record("new-phone-call"),
        "channel": "voice call",
        "language": "RU",
        "audio_url": "https://audio.example.test/call.mp3?token=fixture-only",
        "transcript": [
            {
                "speaker": "client",
                "timestamp": "00:00:02.250",
                "text": "Не получается вывести деньги.",
            },
            {
                "speaker": "operator",
                "timestamp": "00:00:05.500",
                "text": "Здравствуйте. Проверим заявку.",
            },
        ],
    }
    dialogs = normalize_records(
        {"isSuccess": True, "data": {"records": [record(), call]}}, default_checklist(), 3
    )
    assert dialogs[0]["channel"] == "chat"
    result = dialogs[1]
    assert result["channel"] == "call"
    assert result["audio_url"] == call["audio_url"]
    assert result["messages"] == [
        {
            "id": "m1",
            "role": "client",
            "time": "00:00:02.250",
            "text": call["transcript"][0]["text"],
        },
        {
            "id": "m2",
            "role": "operator",
            "time": "00:00:05.500",
            "text": call["transcript"][1]["text"],
        },
    ]
    assert result["status"] == "pending"
    assert result["score"] is None
    assert result["results"] == []


@pytest.mark.parametrize(
    "audio",
    [
        123,
        "https://",
        "https://user:pass@audio.example.test/call.mp3",
        "https://audio.example.test:bad/call.mp3",
    ],
)
def test_invalid_phone_audio_urls_are_explicit_input_errors(audio):
    with pytest.raises(ValueError):
        normalize_records(
            [dict(record(), channel="voice call", audio_url=audio)], default_checklist(), 1
        )


def test_audio_only_call_does_not_receive_fabricated_transcript_or_score():
    with pytest.raises(ValueError, match="расшифровка"):
        normalize_records(
            [dict(record(), channel="voice call", transcript=[])], default_checklist(), 1
        )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"data": None},
        [None],
        [dict(record(), transcript=None)],
        [dict(record(), transcript=["invalid"])],
        [dict(record(), conversation_id=[])],
        [dict(record(), audio_url="javascript:alert(1)")],
    ],
)
def test_bad_inputs_fail_explicitly(payload):
    with pytest.raises(ValueError):
        normalize_records(payload, default_checklist(), 1)


def test_cli_import_and_export_are_durable(tmp_path, monkeypatch):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([record()]))
    db = tmp_path / "db.sqlite3"
    monkeypatch.setenv("CQA_DB", str(db))
    subprocess.run([sys.executable, "-m", "cqa", "import", str(path)], check=True)
    store = Store(str(db))
    assert len(read_workspace(store)["data"]["dialogs"]) == 1
    output = tmp_path / "report.json"
    subprocess.run([sys.executable, "-m", "cqa", "export", str(output)], check=True)
    assert json.loads(output.read_text(encoding="utf-8"))["conversations"][0]["score"] is None
    failed = subprocess.run([sys.executable, "-m", "cqa", "import", str(path)], check=False)
    assert failed.returncode == 1
    assert read_workspace(store)["revision"] == 1


def test_cli_refuses_to_overwrite_browser_changes(tmp_path):
    store = Store(str(tmp_path / "db"))
    data = {"dialogs": [], "criteria": default_checklist(), "version": 1, "appeals": []}
    write_workspace(store, 0, data)
    with pytest.raises(ValueError):
        write_workspace(store, 0, {**data, "version": 2})
    assert read_workspace(store)["data"]["version"] == 1
