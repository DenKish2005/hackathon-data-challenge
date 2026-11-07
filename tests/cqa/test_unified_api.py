import json
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from cqa import api
from cqa.backend.config import Settings
from cqa.backend.main import app as foundation_app
from cqa.backend.main import create_app
from cqa.backend.models import Conversation, Evaluation, EvaluationJob, WorkspaceState
from cqa.infra.llm.ollama import OllamaProvider
from cqa.infra.orchestrator.pipeline import Pipeline, ProviderCritic, ProviderEvaluator

from .test_foundation_data import dataset_payload


def synthetic_app(tmp_path, *, failure=None):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        content = json.loads(body["messages"][1]["content"])["evaluation"]
        first = content["messages"][0]
        result = {
            "summary": "Synthetic HTTP contract, no semantic assessment",
            "results": [
                {
                    "criterionId": c["id"],
                    "answer": min(c["scale"]) if c["type"] == "scale" else "Нет",
                    "reason": "Synthetic contract finding with checked messages",
                    "evidenceId": first["id"],
                    "quote": first["text"],
                    "checkedMessageIds": [m["id"] for m in content["messages"]],
                    "confidence": 0.5,
                }
                for c in content["criteria"]
            ],
        }
        if failure == "quote":
            result["results"][0]["quote"] = "Invented quote"
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "length" if failure == "length" else "stop",
                "message": {"content": "{" if failure == "json" else json.dumps(result)},
                "prompt_eval_count": 100,
                "eval_count": 50,
            },
        )

    provider = OllamaProvider(
        "http://localhost:11434", "synthetic-http-model", transport=httpx.MockTransport(handler)
    )
    evaluator = ProviderEvaluator(provider)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'unified.db'}", timeout=2)
    return (
        create_app(settings, Pipeline(evaluator, critic=ProviderCritic(evaluator))),
        calls,
        settings,
    )


def import_one(client):
    payload = dataset_payload()
    payload["data"]["records"] = payload["data"]["records"][:1]
    payload["data"]["total_records"] = 1
    assert client.post("/api/datasets/import", json={"payload": payload}).status_code == 200
    return client.get("/api/workspace").json()


def evaluate_request(workspace):
    data = workspace["data"]
    dialog = data["dialogs"][0]
    return {
        "conversation_id": dialog["id"],
        "language": dialog["language"],
        "messages": dialog["messages"],
        "criteria": data["criteria"],
        "version": data["version"],
    }


def test_asgi_alias_is_identical():
    assert api.app is foundation_app


def test_single_entry_point_hosts_frontend_and_api(tmp_path):
    static = tmp_path / "frontend"
    static.mkdir()
    (static / "index.html").write_text("<html>synthetic frontend host</html>")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'static.db'}", frontend_dir=str(static)
    )
    with TestClient(create_app(settings)) as client:
        assert "synthetic frontend host" in client.get("/").text
        assert client.get("/api/health").json()["is_mock"] is True
        assert client.get("/docs").status_code == 200


def test_legacy_and_canonical_endpoints_share_jobs_scores_reviews_and_restart(tmp_path):
    app, calls, settings = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        request = evaluate_request(workspace)
        response = client.post("/api/evaluate", json=request)
        assert response.status_code == 200, response.text
        original = response.json()
        assert original["score"] == 0
        assert original["is_mock"] is False
        assert original["tokens"] == 300
        assert original["passes"] == 2
        assert original["results"][0]["evidenceId"] == "m1"
        assert original["results"][0]["confidence"] is None
        assert original["metadata"]["prompt_version"] == "foundation-v1"
        assert len(calls) == 2
        job = client.post(
            "/api/evaluations",
            json={
                "conversation_id": request["conversation_id"],
                "checklist_id": "official",
                "checklist_version": 1,
            },
        ).json()
        assert job["job_id"] == original["jobId"]
        assert job["evaluation_id"] == original["evaluationId"]
        assert client.post("/api/evaluate", json=request).json()["cached"] is True
        assert len(calls) == 2
        workspace = client.get("/api/workspace").json()
        dialog = workspace["data"]["dialogs"][0]
        assert dialog["score"] == original["score"]
        workspace["data"]["appeals"] = [
            {
                "id": "ui-appeal",
                "dialogId": dialog["id"],
                "criterionId": "1",
                "comment": "Please review",
                "status": "open",
                "evidenceId": "m1",
            }
        ]
        assert client.put("/api/workspace", json=workspace).json() == {"revision": 1}
        # Existing frontend edits the answer locally and saves a resolved appeal.
        workspace["revision"] = 1
        workspace["data"]["appeals"][0].update(
            status="resolved", newAnswer="Да", decision="Human confirms greeting"
        )
        workspace["data"]["dialogs"][0]["score"] = 999  # Browser scores never become authoritative.
        assert client.put("/api/workspace", json=workspace).status_code == 200
        canonical = client.get(f"/api/evaluations/{original['evaluationId']}").json()
        assert canonical["result_json"]["score"] == 0
        assert canonical["final_result_json"]["score"] == 10
        assert client.post("/api/evaluate", json=request).json()["score"] == 10
        assert client.get("/api/workspace").json()["data"]["dialogs"][0]["score"] == 10
        assert client.get(f"/api/history/{dialog['id']}").json()[0]["score"] == 0
        persisted = client.get("/api/workspace").json()
        assert persisted["data"]["dialogs"][0]["originalResults"] == original["results"]
        with app.state.db.sessions() as session:
            body = session.get(WorkspaceState, 1).body["dialogs"][0]
            assert "results" not in body and "score" not in body
            assert body["messages"] == [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}, {"id": "m4"}]
    with TestClient(create_app(settings, app.state.pipeline)) as client:
        assert client.get("/api/workspace").json() == persisted
        assert client.get(f"/api/evaluations/{original['evaluationId']}").json() == canonical


def test_ui_checklist_edits_force_and_parallel_requests_preserve_original(tmp_path):
    app, calls, _ = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        request = evaluate_request(workspace)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post("/api/evaluate", json=request), range(2)))
        assert all(r.status_code == 200 for r in results)
        assert len({r.json()["evaluationId"] for r in results}) == 1
        assert len(calls) == 2
        first = results[0].json()
        workspace["data"]["version"] = 2
        workspace["data"]["criteria"][0]["title"] = "Changed greeting"
        assert client.put("/api/workspace", json=workspace).status_code == 200
        request = evaluate_request(workspace)
        second = client.post("/api/evaluate", json=request).json()
        assert second["evaluationId"] != first["evaluationId"]
        forced = client.post("/api/evaluate", json={**request, "force": True})
        assert forced.status_code == 200, forced.text
        assert forced.json()["evaluationId"] != second["evaluationId"]
        assert (
            client.post("/api/evaluate", json=request).json()["evaluationId"]
            == forced.json()["evaluationId"]
        )
        assert len(calls) == 6
        assert (
            client.get(f"/api/evaluations/{first['evaluationId']}").json()["result_json"]["score"]
            == 0
        )
        assert (
            client.get("/api/checklists/official/versions/1").json()["criteria"][0]["title"]
            != "Changed greeting"
        )
        request["criteria"][0]["weight"] = 42
        assert client.post("/api/evaluate", json=request).status_code == 409


def test_failed_model_has_failed_job_and_no_fake_evaluation(tmp_path):
    for failure in ("json", "quote", "length"):
        folder = tmp_path / failure
        folder.mkdir()
        app, _, _ = synthetic_app(folder, failure=failure)
        with TestClient(app) as client:
            workspace = import_one(client)
            response = client.post("/api/evaluate", json=evaluate_request(workspace))
            assert response.status_code == 502
            expected = (
                "Result failed schema or evidence validation; no evaluation saved"
                if failure == "quote"
                else "LLM returned invalid or truncated output; no evaluation saved"
            )
            assert response.json() == {"detail": expected}
            with app.state.db.sessions() as session:
                assert session.scalar(select(func.count()).select_from(Evaluation)) == 0
                assert session.scalar(select(EvaluationJob)).status == "failed"
            assert client.get("/api/workspace").json()["data"]["dialogs"][0]["status"] == "pending"


def test_workspace_save_rolls_back_import_checklist_and_revision_on_invalid_data(tmp_path):
    app, _, _ = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        workspace["data"]["dialogs"][0]["id"] = "new-local"
        workspace["data"]["version"] = 2
        workspace["data"]["criteria"][0]["title"] = "Must roll back"
        workspace["data"]["appeals"] = [
            {
                "id": "bad",
                "dialogId": "new-local",
                "criterionId": "1",
                "comment": "No evaluation",
                "status": "open",
            }
        ]
        assert client.put("/api/workspace", json=workspace).status_code == 409
        assert client.get("/api/workspace").json()["revision"] == 0
        assert client.get("/api/checklists/official").json()["version"] == 1
        with app.state.db.sessions() as session:
            assert session.get(Conversation, "new-local") is None
        request = evaluate_request(workspace)
        request["conversation_id"] = "synthetic-0"
        request["messages"][0]["text"] = "Changed private source"
        assert client.post("/api/evaluate", json=request).status_code == 409


def test_workspace_ui_import_and_explicit_saved_version(tmp_path):
    app, _, _ = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        request = evaluate_request(workspace)
        request["checklist_id"] = "official"
        assert client.post("/api/evaluate", json=request).status_code == 200
        workspace["data"]["dialogs"][0]["id"] = "uploaded-in-browser"
        workspace["data"]["dialogs"][0]["source"] = "organizer"
        assert client.put("/api/workspace", json=workspace).status_code == 200
        assert client.get("/api/conversations/uploaded-in-browser").status_code == 200
        assert (
            client.options(
                "/api/workspace",
                headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT"},
            ).status_code
            == 200
        )


def test_new_ui_version_with_same_criteria_still_creates_a_new_job(tmp_path):
    app, calls, _ = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        first = client.post("/api/evaluate", json=evaluate_request(workspace)).json()
        workspace["data"]["version"] = 2
        assert client.put("/api/workspace", json=workspace).status_code == 200
        second = client.post("/api/evaluate", json=evaluate_request(workspace)).json()
        assert first["evaluationId"] != second["evaluationId"]
        assert second["foundationChecklistVersion"] == 2
        assert len(calls) == 4


def test_critic_switch_changes_pipeline_cache_configuration(tmp_path):
    options = dict(
        database_url=f"sqlite:///{tmp_path / 'toggle.db'}",
        llm_provider="ollama",
        llm_base_url="http://localhost:11434",
        llm_model="test",
    )
    enabled = create_app(Settings(**options), worker_enabled=False)
    disabled = create_app(Settings(**options, critic_enabled=False), worker_enabled=False)
    assert enabled.state.pipeline.critic is not None
    assert disabled.state.pipeline.critic is None
    assert enabled.state.pipeline.configuration() != disabled.state.pipeline.configuration()
    enabled.state.db.engine.dispose()
    disabled.state.db.engine.dispose()


def test_later_opposing_review_does_not_rewrite_or_block_earlier_review(tmp_path):
    app, _, _ = synthetic_app(tmp_path)
    with TestClient(app) as client:
        workspace = import_one(client)
        response = client.post("/api/evaluate", json=evaluate_request(workspace))
        assert response.status_code == 200
        workspace = client.get("/api/workspace").json()
        dialog = workspace["data"]["dialogs"][0]
        workspace["data"]["appeals"] = [
            {
                "id": "first",
                "dialogId": dialog["id"],
                "criterionId": "1",
                "comment": "First review",
                "status": "resolved",
                "newAnswer": "Да",
                "decision": "First human decision",
                "evidenceId": "m1",
            }
        ]
        assert client.put("/api/workspace", json=workspace).status_code == 200
        workspace = client.get("/api/workspace").json()
        workspace["data"]["appeals"].append(
            {
                "id": "second",
                "dialogId": dialog["id"],
                "criterionId": "1",
                "comment": "Second review",
                "status": "resolved",
                "newAnswer": "Нет",
                "decision": "Second human decision",
                "evidenceId": "m1",
            }
        )
        assert client.put("/api/workspace", json=workspace).status_code == 200
        workspace = client.get("/api/workspace").json()
        assert [a["newAnswer"] for a in workspace["data"]["appeals"]] == ["Да", "Нет"]
        assert workspace["data"]["dialogs"][0]["score"] == 0
        assert client.put("/api/workspace", json=workspace).status_code == 200
