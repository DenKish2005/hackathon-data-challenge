from urllib.parse import quote

from fastapi.testclient import TestClient

from cqa import api
from cqa.benchmark import compare
from cqa.service import Store


def test_workspace_persistence_conflict_and_api_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(api.evaluator, "store", Store(str(tmp_path / "db")))
    with TestClient(api.app) as client:
        assert client.get("/api/workspace").json() == {"revision": 0, "data": None}
        payload = {"revision": 0, "data": {"appeals": [{"id": "a", "status": "open"}]}}
        assert client.put("/api/workspace", json=payload).json() == {"revision": 1}
        assert client.put("/api/workspace", json=payload).status_code == 409
        assert client.get("/api/workspace").json()["data"] == payload["data"]
        assert client.post("/api/evaluate", json={}).status_code == 422
        assert client.get("/api/history/new").json() == []


def test_history_preserves_conversation_ids_with_slashes(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "db"))
    monkeypatch.setattr(api.evaluator, "store", store)
    expected = {"evaluationId": "target", "conversation_id": "DEV/chat/1", "score": 90}
    store.save("target-key", expected)
    store.save("other-key", {"evaluationId": "other", "conversation_id": "DEV/chat/2"})

    with TestClient(api.app) as client:
        response = client.get("/api/history/" + quote(expected["conversation_id"], safe=""))
        assert response.status_code == 200
        assert response.json() == [expected]


def test_benchmark_counts_missing_as_wrong():
    truth = [
        {"conversation_id": "a", "score": 90, "results": [{"criterionId": "1", "answer": "Да"}]},
        {"conversation_id": "b", "score": 50, "results": [{"criterionId": "1", "answer": "Нет"}]},
    ]
    result = compare([{"conversation_id": "a", "score": 80, "results": truth[0]["results"]}], truth)
    assert result["criterion_accuracy"] == 0.5
    assert result["score_mae"] == 10
    assert result["missing_dialogues"] == ["b"]
