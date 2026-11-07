import time
from urllib.parse import quote

from fastapi.testclient import TestClient

from cqa.backend.config import Settings
from cqa.backend.main import create_app
from cqa.backend.models import Conversation, Message
from cqa.infra.orchestrator.pipeline import MockEvaluator, Pipeline

from .test_unified_api import evaluate_request, import_one


def poll(client, job_id):
    for _ in range(100):
        response = client.get(f"/api/workspace-evaluations/{job_id}")
        assert response.status_code == 200, response.text
        view = response.json()
        if view["status"] in ("completed", "failed"):
            return view
        time.sleep(0.02)
    raise AssertionError("Synthetic background job did not finish")


def test_async_submission_is_durable_nonblocking_and_reuses_completed_job(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'async.db'}")
    # With no worker, submission must still return immediately and retain the job.
    with TestClient(create_app(settings, worker_enabled=False)) as client:
        workspace = import_one(client)
        request = evaluate_request(workspace)
        accepted = client.post("/api/evaluate?async_job=true", json=request)
        assert accepted.status_code == 202, accepted.text
        job = accepted.json()
        assert job["status"] == "pending"
        assert job["cached"] is False
        assert accepted.headers["location"] == f"/api/workspace-evaluations/{job['jobId']}"
        assert client.get(accepted.headers["location"]).json() == {
            "jobId": job["jobId"],
            "status": "pending",
        }
        duplicate = client.post("/api/evaluate?async_job=true", json=request).json()
        assert duplicate["jobId"] == job["jobId"]

    # Restart a fresh application using only the persisted canonical database.
    with TestClient(create_app(settings)) as client:
        done = poll(client, job["jobId"])
        assert done["status"] == "completed"
        result = done["result"]
        assert result["jobId"] == job["jobId"]
        assert result["conversation_id"] == request["conversation_id"]
        assert result["is_mock"] is True
        assert len(result["results"]) == 8
        assert result["criteriaSnapshot"] == request["criteria"]
        assert result["messages"] == request["messages"]
        cached = client.post("/api/evaluate?async_job=true", json=request).json()
        assert cached == {"jobId": job["jobId"], "status": "completed", "cached": True}
        sync = client.post("/api/evaluate", json=request)
        assert sync.status_code == 200
        assert sync.json()["evaluationId"] == result["evaluationId"]
        assert sync.json()["cached"] is True


def test_async_failed_job_explains_failure_without_private_exception(tmp_path):
    class FailingEvaluator(MockEvaluator):
        async def evaluate_conversation(self, conversation, checklist):
            raise RuntimeError("private transcript and https://private.test/?sig=secret")

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'failure.db'}")
    with TestClient(create_app(settings, Pipeline(FailingEvaluator()))) as client:
        request = evaluate_request(import_one(client))
        accepted = client.post("/api/evaluate?async_job=true", json=request)
        assert accepted.status_code == 202
        done = poll(client, accepted.json()["jobId"])
        assert done["status"] == "failed"
        assert done["error"] == "Evaluation failed"
        assert "result" not in done
        assert "private" not in str(done)
        assert client.get("/api/workspace-evaluations/missing").status_code == 404


def test_history_with_encoded_slashes_uses_full_conversation_identity(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'slash.db'}")
    app = create_app(settings)
    with TestClient(app) as client:
        request = evaluate_request(import_one(client))
        request["conversation_id"] = "DEV/chat/1"
        # Persist a legacy identity directly: the new import schema intentionally
        # restricts identifiers, but history must still address pre-existing IDs.
        with app.state.db.sessions.begin() as session:
            session.add(
                Conversation(
                    conversation_id=request["conversation_id"],
                    dataset_group_id="legacy-synthetic",
                    language=request["language"],
                    channel="agent chat",
                    audio_url=None,
                    original_payload={},
                )
            )
            session.flush()
            for index, message in enumerate(request["messages"]):
                session.add(
                    Message(
                        message_id=f"legacy-{index}",
                        conversation_id=request["conversation_id"],
                        message_index=index,
                        speaker=message["role"],
                        timestamp_original=message["time"],
                        text=message["text"],
                    )
                )
        evaluated = client.post("/api/evaluate", json=request)
        assert evaluated.status_code == 200, evaluated.text
        history = client.get("/api/history/" + quote("DEV/chat/1", safe=""))
        assert history.status_code == 200
        assert [r["evaluationId"] for r in history.json()] == [evaluated.json()["evaluationId"]]
        assert client.get("/api/history/DEV/chat/other").json() == []
