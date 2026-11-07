import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from cqa.backend.config import Settings
from cqa.backend.main import create_app
from cqa.infra.orchestrator.pipeline import MockEvaluator, Pipeline

from .test_foundation_data import dataset_payload


def import_local(client):
    response = client.post("/api/datasets/import", json={"payload": dataset_payload()})
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 65


def test_rest_crud_contracts_versions_cors_and_redacted_validation(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(settings, worker_enabled=False)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/api/health").json()["is_mock"] is True
        import_local(client)
        assert (
            client.post("/api/datasets/import", json={"payload": dataset_payload()}).json()[
                "skipped"
            ]
            == 65
        )
        assert len(client.get("/api/conversations").json()) == 65
        assert len(client.get("/api/conversations?language=KZ").json()) == 15
        assert len(client.get("/api/conversations?channel=voice%20call").json()) == 5
        assert len(client.get("/api/conversations?offset=60&limit=10").json()) == 5
        call = client.get("/api/conversations/synthetic-64").json()
        assert call["audio_url"] == "https://example.test/64.mp3"
        assert call["messages"][0]["timestamp_original"] == "2026-01-01T12:00:00.123456+05:00"
        assert "original_payload" not in call
        first = client.get("/api/checklists/official").json()
        assert len(first["criteria"]) == 8
        new = {"checklist_id": "official", "base_version": 1, "criteria": first["criteria"]}
        new["criteria"][0]["title"] = "Updated title"
        assert client.post("/api/checklists", json=new).json()["version"] == 2
        assert client.post("/api/checklists", json=new).status_code == 409
        assert (
            client.get("/api/checklists/official/versions/1").json()["criteria"][0]["title"]
            != "Updated title"
        )
        assert client.get("/api/checklists").json()[0]["version"] == 2
        assert client.get("/api/conversations/missing").status_code == 404
        assert client.get("/api/evaluation-jobs/missing").status_code == 404
        response = client.post("/api/datasets/import", json={"url": "https://private?sig=secret"})
        assert response.status_code == 422
        assert "secret" not in response.text
        assert (
            client.options(
                "/api/conversations",
                headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
            ).headers["access-control-allow-origin"]
            == "http://localhost:5173"
        )
        assert (
            "access-control-allow-origin"
            not in client.get(
                "/api/conversations", headers={"Origin": "https://untrusted.test"}
            ).headers
        )
        assert (
            client.post(
                "/api/evaluations",
                json={
                    "conversation_id": "missing",
                    "checklist_id": "official",
                    "checklist_version": 1,
                },
            ).status_code
            == 404
        )


def wait_completed(client, job_id):
    for _ in range(100):
        job = client.get(f"/api/evaluation-jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            assert job["status"] == "completed", job
            return job
        time.sleep(0.02)
    raise AssertionError("Worker did not finish synthetic job")


def test_real_worker_appeals_and_restart_persistence(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(settings)
    with TestClient(app) as client:
        import_local(client)
        request = {
            "conversation_id": "synthetic-0",
            "checklist_id": "official",
            "checklist_version": 1,
        }
        response = client.post("/api/evaluations", json=request)
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert client.post("/api/evaluations", json=request).json()["job_id"] == job_id
        job = wait_completed(client, job_id)
        evaluation_id = job["evaluation_id"]
        original = client.get(f"/api/evaluations/{evaluation_id}").json()
        assert original["is_mock"] is True
        appeal = client.post(
            "/api/appeals",
            json={
                "evaluation_id": evaluation_id,
                "criterion_id": "1",
                "comment": "Review greeting",
            },
        ).json()
        appeal_id = appeal["appeal_id"]
        assert client.get(f"/api/appeals/{appeal_id}").json()["status"] == "open"
        review = {
            "decision": "accepted",
            "reason": "Human decision",
            "base_revision": 0,
            "replacement": {
                "criterion_id": "1",
                "answer": "Да",
                "explanation": "Human review",
                "message_ids": [original["result_json"]["findings"][0]["checked_message_ids"][0]],
            },
        }
        assert client.post(f"/api/appeals/{appeal_id}/review", json=review).status_code == 200
        assert client.post(f"/api/appeals/{appeal_id}/review", json=review).status_code == 409
        final = client.get(f"/api/evaluations/{evaluation_id}").json()
        assert final["result_json"] == original["result_json"]
        assert final["final_result_json"]["score"] == 10
        assert len(client.get(f"/api/evaluations/{evaluation_id}/reviews").json()) == 1
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/api/conversations").json()) == 65
        assert client.get(f"/api/evaluations/{evaluation_id}").json() == final


def test_running_job_resumes_after_actual_lifespan_restart(tmp_path):
    class SlowMock(MockEvaluator):
        async def evaluate_conversation(self, conversation, checklist):
            await asyncio.sleep(100)

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(create_app(settings, Pipeline(SlowMock()))) as client:
        import_local(client)
        job = client.post(
            "/api/evaluations",
            json={
                "conversation_id": "synthetic-0",
                "checklist_id": "official",
                "checklist_version": 1,
            },
        ).json()
        for _ in range(100):
            if client.get(f"/api/evaluation-jobs/{job['job_id']}").json()["status"] == "running":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("Job did not start")
    with TestClient(create_app(settings)) as client:
        assert wait_completed(client, job["job_id"])["attempts"] == 2


def test_organizer_uses_configured_url_verbatim_and_rejects_other_hosts(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=dataset_payload())

    url = "https://environment.api.powerplatform.com/private?sig=synthetic&group_id=DEV"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}", organizer_urls={"DEV": url}
    )
    with TestClient(
        create_app(settings, worker_enabled=False, transport=httpx.MockTransport(handler))
    ) as client:
        assert client.post("/api/datasets/import", json={"source": "organizer"}).status_code == 200
        assert seen == [url]
        assert (
            client.post(
                "/api/datasets/import", json={"source": "organizer", "group_id": "CONTROL"}
            ).status_code
            == 404
        )
        settings.organizer_urls["DEV"] = "http://127.0.0.1/private"
        assert client.post("/api/datasets/import", json={"source": "organizer"}).status_code == 502
        assert seen == [url]


@pytest.mark.parametrize(
    "body",
    [
        {"isSuccess": False},
        {"unexpected": "secret"},
        {**dataset_payload(), "data": {"records": []}},
    ],
)
def test_invalid_organizer_responses_are_redacted(tmp_path, body):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        organizer_urls={"DEV": "https://environment.api.powerplatform.com/private?sig=secret"},
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    with TestClient(create_app(settings, worker_enabled=False, transport=transport)) as client:
        response = client.post("/api/datasets/import", json={"source": "organizer"})
        assert response.status_code == 502
        assert "secret" not in response.text
