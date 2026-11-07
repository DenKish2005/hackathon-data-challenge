"""Isolated synthetic integration tests. No organizer secrets or real conversations."""
import time
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from cqa.backend.config import Settings
from cqa.backend.main import create_app


def fake_dataset(group="DEV", count=65):
    records = []
    for i in range(count):
        voice = i >= 60
        language = "RU" if i < 35 else ("KZ" if i < 50 else "EN")
        num_messages = 20 if i < 33 else 19
        messages = [{"speaker": ("client" if j % 2 == 0 else "operator"),
                     "timestamp": (f"2026-11-07T13:00:{j % 60:02d}.123+05:00" if voice else f"00:{j % 60:02d}"),
                     "text": f"Fictional message {i}/{j}"} for j in range(num_messages)]
        records.append({"conversation_id": f"p-{i:03}", "channel": "voice call" if voice else "agent chat",
                        "language": language, "transcript": messages,
                        "audio_url": f"https://example.invalid/audio/{i}" if voice else None})
    return {"error": "", "isSuccess": True,
            "data": {"dataset_group_id": group, "total_records": count, "records": records}}


@pytest.fixture
def client(tmp_path):
    config = replace(Settings(), database_url=f"sqlite:///{tmp_path / 'data.sqlite'}", dataset_path=str(tmp_path / 'missing.json'), worker_poll_seconds=0.02)
    with TestClient(create_app(config)) as c:
        yield c


def test_dataset_import_idempotent_and_preserves_roles_times_audio(client):
    payload = fake_dataset()
    one = client.post("/api/datasets/import", json={"source": "payload", "group_id": "DEV", "payload": payload})
    assert one.status_code == 200, one.text
    assert one.json()["created"] == 65
    assert one.json()["messages"] == 1268
    two = client.post("/api/datasets/import", json={"source": "payload", "group_id": "DEV", "payload": payload})
    assert two.json()["unchanged"] == 65 and two.json()["created"] == 0
    listing = client.get("/api/conversations?limit=100").json()
    assert listing["total"] == 65
    assert sum(c["channel"] == "voice call" for c in listing["items"]) == 5
    assert {lang: sum(c["language"] == lang for c in listing["items"]) for lang in ("RU", "KZ", "EN")} == {"RU": 35, "KZ": 15, "EN": 15}
    conv = client.get("/api/conversations/p-060?group_id=DEV").json()
    assert conv["audio_url"].endswith("/60")
    assert ".123+05:00" in conv["messages"][0]["timestamp_original"]
    assert [m["message_index"] for m in conv["messages"]] == list(range(len(conv["messages"])))
    assert len({m["message_id"] for m in conv["messages"]}) == len(conv["messages"])
    assert client.get("/api/conversations/p-060").json()["messages"][0]["message_id"] == conv["messages"][0]["message_id"]


def test_dataset_import_rejects_invalid_and_group_mismatch(client):
    data = fake_dataset(count=1)
    data["data"]["records"][0]["transcript"][0]["speaker"] = "other"
    assert client.post("/api/datasets/import", json={"source": "payload", "payload": data}).status_code == 422
    assert client.post("/api/datasets/import", json={"source": "payload", "group_id": "CONTROL", "payload": fake_dataset(count=1)}).status_code == 422
    assert client.post("/api/datasets/import", json={"source": "api"}).status_code == 503
    assert client.post("/api/datasets/import", json={"source": "local"}).status_code == 404


def test_checklist_versions_immutable_and_na_validation(client):
    original = client.get("/api/checklists/official").json()
    assert original["version"] == 1
    assert sum(c["weight"] for c in original["criteria"]) == 100
    new_criteria = [dict(c) for c in original["criteria"]]
    new_criteria[0]["weight"] = 9
    updated = client.post("/api/checklists", json={"checklist_id": "official", "criteria": new_criteria, "expected_version": 1})
    assert updated.status_code == 201 and updated.json()["version"] == 2
    assert client.get("/api/checklists/official/versions/1").json()["criteria"][0]["weight"] == 10
    assert client.get("/api/checklists/official").json()["version"] == 2
    assert client.post("/api/checklists", json={"checklist_id": "official", "criteria": new_criteria, "expected_version": 1}).status_code == 409
    new_criteria[0]["type"] = "scale"
    new_criteria[0]["scale"] = [0, 4, 7, 10]
    assert client.post("/api/checklists", json={"checklist_id": "new", "criteria": new_criteria}).status_code == 201


def wait_completed(client, job_id):
    for _ in range(120):
        data = client.get(f"/api/evaluation-jobs/{job_id}").json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.03)
    pytest.fail("worker did not finish")


def test_evaluation_and_appeal_history(client):
    imported = client.post("/api/datasets/import", json={"source": "payload", "payload": fake_dataset(count=1)})
    assert imported.status_code == 200
    created = client.post("/api/evaluations", json={"conversation_id": "p-000", "group_id": "DEV"})
    assert created.status_code == 202, created.text
    j = wait_completed(client, created.json()["job_id"])
    assert j["status"] == "completed", j
    duplicate = client.post("/api/evaluations", json={"conversation_id": "p-000", "group_id": "DEV"})
    assert duplicate.json()["job_id"] == j["job_id"]
    evaluation = client.get("/api/evaluations/" + j["evaluation_id"]).json()
    assert evaluation["is_mock"] and evaluation["result_json"]["total_score"] is None
    assert evaluation["result_json"]["checklist_snapshot"]["version"] == 1
    assert evaluation["result_json"]["criteria"][0]["evidence_message_ids"] == []
    appeal = client.post("/api/appeals", json={"evaluation_id": j["evaluation_id"], "criterion_id": "04", "comment": "Please review"})
    assert appeal.status_code == 201
    aid = appeal.json()["appeal_id"]
    assert client.post(f"/api/appeals/{aid}/review", json={"decision": "upheld", "reason": "Recheck", "revised_answer": 12}).status_code == 422
    reviewed = client.post(f"/api/appeals/{aid}/review", json={"decision": "upheld", "reason": "Review corrected answer", "revised_answer": 15})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["final_answer"] == 15 and len(reviewed.json()["history"]) == 1
    assert client.post(f"/api/appeals/{aid}/review", json={"decision": "rejected", "reason": "no"}).status_code == 409
    after = client.get("/api/evaluations/" + j["evaluation_id"]).json()
    assert after["result_json"] == evaluation["result_json"]


def test_job_survives_restart(tmp_path):
    config = replace(Settings(), database_url=f"sqlite:///{tmp_path / 'persist.sqlite'}", worker_poll_seconds=0.02)
    with TestClient(create_app(config)) as client:
        assert client.post("/api/datasets/import", json={"source": "payload", "payload": fake_dataset(count=1)}).status_code == 200
        job_id = client.post("/api/evaluations", json={"conversation_id": "p-000"}).json()["job_id"]
        assert wait_completed(client, job_id)["status"] == "completed"
    with TestClient(create_app(config)) as client:
        assert client.get(f"/api/evaluation-jobs/{job_id}").json()["status"] == "completed"
        assert client.get("/api/conversations").json()["total"] == 1


def test_import_update_and_ambiguous_group(client):
    old = fake_dataset(count=1)
    assert client.post("/api/datasets/import", json={"source": "payload", "payload": old}).status_code == 200
    first_id = client.get("/api/conversations/p-000?group_id=DEV").json()["messages"][0]["message_id"]
    changed = fake_dataset(count=1)
    changed["data"]["records"][0]["transcript"][0]["text"] = "Edited synthetic message"
    response = client.post("/api/datasets/import", json={"source": "payload", "payload": changed})
    assert response.json()["updated"] == 1
    after = client.get("/api/conversations/p-000?group_id=DEV").json()
    assert after["messages"][0]["message_id"] == first_id
    assert after["messages"][0]["text"] == "Edited synthetic message"
    control = fake_dataset(group="CONTROL", count=1)
    assert client.post("/api/datasets/import", json={"source": "payload", "group_id": "CONTROL", "payload": control}).status_code == 200
    assert client.get("/api/conversations/p-000").status_code == 409
    assert client.get("/api/conversations/p-000?group_id=CONTROL").status_code == 200


def test_failed_evaluation_marks_job_and_does_not_fabricate_result(tmp_path):
    class BrokenEvaluator:
        name = "broken"
        model_name = "broken"
        prompt_version = "v1"

        async def evaluate_conversation(self, conversation, checklist):
            raise TimeoutError("Private upstream credentials and URL should not be exposed")

    cfg = replace(Settings(), database_url=f"sqlite:///{tmp_path / 'failure.db'}", worker_poll_seconds=0.01)
    with TestClient(create_app(cfg, evaluator=BrokenEvaluator())) as client:
        client.post("/api/datasets/import", json={"source": "payload", "payload": fake_dataset(count=1)})
        job_id = client.post("/api/evaluations", json={"conversation_id": "p-000"}).json()["job_id"]
        result = wait_completed(client, job_id)
        assert result["status"] == "failed"
        assert "Private" not in result["error_message"]
        assert result["evaluation_id"] is None
