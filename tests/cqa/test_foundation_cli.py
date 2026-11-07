import json
import os
import subprocess
import sys
from types import SimpleNamespace

import httpx

from cqa.backend.__main__ import evaluate

from .test_foundation_data import dataset_payload


def test_standalone_cli_imports_private_local_file_idempotently(tmp_path):
    path = tmp_path / "private.json"
    path.write_text(json.dumps(dataset_payload(), ensure_ascii=False), encoding="utf-8-sig")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'cli.db'}"}
    command = [sys.executable, "-m", "cqa.backend", "import", str(path)]
    first = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert json.loads(first.stdout)["imported"] == 65
    second = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert json.loads(second.stdout)["skipped"] == 65
    path.write_text('{"private": "secret"}', encoding="utf-8")
    invalid = subprocess.run(command, env=env, capture_output=True, text=True)
    assert invalid.returncode == 1
    assert "secret" not in invalid.stderr


def test_batch_cli_uses_server_jobs_and_final_scores(monkeypatch, capsys):
    paths = []

    def handler(request):
        paths.append((request.method, request.url.path))
        if request.url.path == "/api/checklists/official":
            data = {"version": 2}
        elif request.url.path == "/api/conversations":
            data = [{"conversation_id": "synthetic"}]
        elif request.method == "POST":
            body = json.loads(request.content)
            assert body["checklist_version"] == 2
            assert body["force"] is False
            data = {"job_id": "j", "status": "pending"}
        elif request.url.path == "/api/evaluation-jobs/j":
            data = {"job_id": "j", "status": "completed", "evaluation_id": "e"}
        else:
            data = {"final_result_json": {"score": 10}}
        return httpx.Response(200, json=data)

    client = httpx.Client(base_url="http://synthetic.test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr("cqa.backend.__main__.httpx.Client", lambda **kwargs: client)
    monkeypatch.setattr("cqa.backend.__main__.time.sleep", lambda _: None)
    args = SimpleNamespace(
        api_url="http://synthetic.test",
        checklist_id="official",
        version=None,
        id=None,
        limit=1,
        timeout=1,
        force=False,
        retry_failed=False,
    )
    assert evaluate(args) == 0
    assert json.loads(capsys.readouterr().out)["score"] == 10
    assert ("POST", "/api/evaluations") in paths
    assert ("GET", "/api/evaluation-jobs/j") in paths
