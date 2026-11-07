from urllib.parse import quote

from fastapi.testclient import TestClient

from cqa import api
from cqa.backend.config import Settings
from cqa.benchmark import compare


def test_workspace_persistence_conflict_and_api_validation(tmp_path):
    app = api.create_app(Settings(database_url=f"sqlite:///{tmp_path / 'db'}"))
    with TestClient(app) as client:
        assert client.get("/api/workspace").json() == {"revision": 0, "data": None}
        payload = {"revision": 0, "data": {"appeals": [{"id": "a", "status": "open"}]}}
        assert client.put("/api/workspace", json=payload).json() == {"revision": 1}
        assert client.put("/api/workspace", json=payload).status_code == 409
        assert client.get("/api/workspace").json()["data"]["appeals"] == payload["data"]["appeals"]
        assert client.post("/api/evaluate", json={}).status_code == 422
        assert client.get("/api/history/new").json() == []


def test_history_uses_canonical_persisted_evaluations(tmp_path):
    app = api.create_app(Settings(database_url=f"sqlite:///{tmp_path / 'history.db'}"))
    request = {
        "conversation_id": "DEV:chat:1",
        "language": "RU",
        "version": 1,
        "messages": [{"id": "m1", "role": "operator", "time": "00:00", "text": "Здравствуйте!"}],
        "criteria": [
            {
                "id": "new-rule",
                "title": "Приветствие",
                "description": "Приветствие оператора",
                "weight": 10,
                "type": "binary",
            }
        ],
    }
    with TestClient(app) as client:
        evaluation = client.post("/api/evaluate", json=request)
        assert evaluation.status_code == 200, evaluation.text
        expected = evaluation.json()
        history = client.get("/api/history/" + quote(request["conversation_id"], safe=""))
        assert history.status_code == 200
        assert history.json()[0]["evaluationId"] == expected["evaluationId"]
        assert history.json()[0]["is_mock"] is True
        assert client.get("/api/history/DEV:chat:2").json() == []
    with TestClient(
        api.create_app(Settings(database_url=f"sqlite:///{tmp_path / 'history.db'}"))
    ) as client:
        assert (
            client.get("/api/history/DEV:chat:1").json()[0]["evaluationId"]
            == expected["evaluationId"]
        )


def test_benchmark_counts_missing_as_wrong():
    truth = [
        {"conversation_id": "a", "score": 90, "results": [{"criterionId": "1", "answer": "Да"}]},
        {"conversation_id": "b", "score": 50, "results": [{"criterionId": "1", "answer": "Нет"}]},
    ]
    result = compare([{"conversation_id": "a", "score": 80, "results": truth[0]["results"]}], truth)
    assert result["criterion_accuracy"] == 0.5
    assert result["score_mae"] == 10
    assert result["missing_dialogues"] == ["b"]
