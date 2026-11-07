import json
from types import SimpleNamespace

import httpx

from cqa.backend.__main__ import evaluate
from cqa.backend.config import Settings
from cqa.backend.services.batch_report import summarize


def test_batch_report_resume_and_failed_only(monkeypatch, tmp_path):
    jobs = {"a": "completed", "b": "failed"}
    submitted = []

    def handler(request):
        path = request.url.path
        if path.endswith("checklists/official"):
            data = {"version": 1}
        elif path.endswith("conversations"):
            assert request.url.params["group_id"] == "CONTROL-NEW"
            data = [{"conversation_id": cid} for cid in jobs]
        elif request.method == "POST":
            body = json.loads(request.content)
            cid = body["conversation_id"]
            submitted.append(cid)
            if body["retry_failed"]:
                jobs[cid] = "completed"
            data = {
                "job_id": cid,
                "status": jobs[cid],
                "evaluation_id": cid,
                "error_message": "Evaluation failed",
            }
        else:
            data = {"final_result_json": {"score": 75}}
        return httpx.Response(200, json=data)

    original = httpx.Client
    monkeypatch.setattr(
        "cqa.backend.__main__.httpx.Client",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )
    args = SimpleNamespace(
        api_url="http://synthetic.test",
        checklist_id="official",
        version=None,
        id=None,
        group_id="CONTROL-NEW",
        limit=None,
        timeout=1,
        force=False,
        retry_failed=False,
        report=tmp_path / "batch.json",
        failed_only=False,
        parallel=2,
    )
    assert evaluate(args) == 1
    report = json.loads(args.report.read_text())
    assert report["summary"]["completed"] == 1
    assert report["summary"]["failed"] == 1
    assert args.report.with_suffix(".csv").exists()
    submitted.clear()
    args.failed_only = True
    assert evaluate(args) == 0
    assert submitted == ["b"]


def test_unknown_tokens_and_cache_do_not_invent_throughput():
    result = summarize([{"status": "completed", "cached": True}], 1, 1)
    assert result["estimated_65_seconds"] is None
    assert result["input_tokens"] is None
    failed = summarize(
        [
            {
                "status": "failed",
                "metrics": [{"status": "failed", "error_code": "validation_error", "calls": []}],
            }
        ],
        1,
        1,
    )
    assert failed["invalid_responses"] == 1
    assert failed["estimated_65_seconds"] is None


def test_new_group_uses_separate_private_full_url(monkeypatch, tmp_path):
    file = tmp_path / "urls.json"
    url = "https://example.environment.api.powerplatform.com/run?sig=private&group_id=NEW"
    file.write_text(json.dumps({"NEW": url}), encoding="utf-8")
    monkeypatch.setenv("FREEDOM_DATASET_URLS_FILE", str(file))
    settings = Settings()
    assert settings.organizer_urls["NEW"] == url
    assert "private" not in repr(settings)


def test_interrupt_writes_report_and_keeps_durable_job_id(monkeypatch, tmp_path):
    def handler(request):
        if request.url.path.endswith("checklists/official"):
            data = {"version": 1}
        else:
            data = {"job_id": "durable", "status": "pending"}
        return httpx.Response(200, json=data)

    original = httpx.Client
    monkeypatch.setattr(
        "cqa.backend.__main__.httpx.Client",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )

    def interrupt(*args, **kwargs):
        import time

        time.sleep(0.05)
        raise KeyboardInterrupt

    monkeypatch.setattr("concurrent.futures.wait", interrupt)
    args = SimpleNamespace(
        api_url="http://synthetic.test",
        checklist_id="official",
        version=1,
        id="a",
        limit=None,
        timeout=5,
        force=False,
        retry_failed=False,
        report=tmp_path / "batch.json",
        failed_only=False,
        parallel=1,
    )
    assert evaluate(args) == 130
    report = json.loads(args.report.read_text())
    assert report["interrupted"]
    assert report["results"][0]["job_id"] == "durable"
    assert report["summary"]["completed"] == 0
