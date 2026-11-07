"""Synthetic live checks for the unified API and local AI acceptance.

By default, check a running Foundation server (--api-url, --full-checklist).
With --output-dir, run isolated in-process API acceptance including cache,
changed criteria, force evaluation and history recovery in a fresh process.
No model download or private dataset upload is performed.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def run_local_smoke(args):
    output = Path(args.output_dir).resolve()
    if any((p / ".git").exists() for p in [output, *output.parents]):
        raise SystemExit("Acceptance outputs must be outside a Git worktree")
    output.mkdir(parents=True, exist_ok=False)
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("LLM_MODEL") or os.getenv("CQA_MODEL", "qwen3:4b-instruct")
    endpoint = urlsplit(base_url)
    model_name = model.lower()
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in ("127.0.0.1", "localhost", "::1")
        or ":cloud" in model_name
        or model_name.endswith("-cloud")
    ):
        raise SystemExit("This acceptance tool permits only local Ollama models")
    from fastapi.testclient import TestClient

    from cqa import api
    from cqa.backend.config import Settings
    from cqa.workspace import normalize_records

    settings = Settings(
        database_url=f"sqlite:///{output / 'app.sqlite3'}",
        llm_provider="ollama",
        llm_base_url=base_url,
        llm_model=model,
        llm_context_size=int(os.getenv("LLM_CONTEXT_SIZE") or os.getenv("CQA_NUM_CTX", "16384")),
        llm_output_limit=int(os.getenv("LLM_OUTPUT_LIMIT") or os.getenv("CQA_NUM_PREDICT", "2000")),
        llm_timeout=args.timeout,
        timeout=args.timeout,
        concurrency=1,
    )
    app = api.create_app(settings)

    source = Path(__file__).resolve().parent
    criteria = json.loads((source / "cqa_replacement_checklist.json").read_text(encoding="utf-8"))
    records = json.loads((source / "cqa_synthetic.json").read_text(encoding="utf-8"))
    dialogs = normalize_records(records, criteria, 1)
    dialog = next((d for d in dialogs if d["id"] == args.conversation_id), None)
    if dialog is None:
        raise SystemExit("Unknown synthetic conversation ID")
    payload = {
        "conversation_id": dialog["id"],
        "language": dialog["language"],
        "messages": dialog["messages"],
        "criteria": criteria,
        "version": 1,
    }
    changed = copy.deepcopy(payload)
    changed["version"] = 2
    changed["criteria"][0].update(
        description="Did the operator explain what to do if the language option is missing? "
        "9=clear fallback, 3=partial, 0=none.",
        scale=[0, 3, 9],
    )
    provider = app.state.pipeline.evaluator.provider
    generate = provider.generate
    calls = 0

    async def capture(messages, schema):
        nonlocal calls
        calls += 1
        response = await generate(messages, schema)
        write_new(
            output / "provider-responses" / f"{calls:04}.json",
            {"analysis": response, "metadata": response.metadata},
        )
        return response

    provider.generate = capture
    outcomes = []
    with TestClient(app) as client:
        for name, request in [
            ("new", payload),
            ("cached", payload),
            ("changed", changed),
            ("fresh", {**payload, "force": True}),
        ]:
            before = calls
            started = time.monotonic()
            response = client.post("/api/evaluate", json=request)
            result = response.json()
            record = {
                "case": name,
                "httpStatus": response.status_code,
                "calls": calls - before,
                "result": result,
            }
            outcomes.append(record)
            print(
                json.dumps(
                    {
                        "case": name,
                        "status": response.status_code,
                        "score": result.get("score"),
                        "calls": calls - before,
                        "seconds": round(time.monotonic() - started, 3),
                    }
                ),
                flush=True,
            )
    write_new(output / "api-results.json", outcomes)
    restart_code = (
        "import json; from fastapi.testclient import TestClient; from cqa.api import app; "
        "\nwith TestClient(app) as c:\n"
        " print(json.dumps([r['evaluationId'] for r in "
        f"c.get({'/api/history/' + quote(dialog['id'], safe='')!r}).json()]))"
    )
    history = json.loads(
        subprocess.check_output(
            [sys.executable, "-c", restart_code],
            text=True,
            env={**os.environ, "DATABASE_URL": settings.database_url, "LLM_PROVIDER": "mock"},
        )
    )
    summary = {
        "allRequestsSucceeded": all(r["httpStatus"] == 200 for r in outcomes),
        "restartHistoryEntries": len(history),
        "modelCalls": calls,
    }
    if outcomes[0]["httpStatus"] == outcomes[-1]["httpStatus"] == 200:
        first = {r["criterionId"]: r["answer"] for r in outcomes[0]["result"]["results"]}
        fresh = {r["criterionId"]: r["answer"] for r in outcomes[-1]["result"]["results"]}
        summary["freshAnswersIdentical"] = first == fresh
    write_new(output / "acceptance.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if summary["allRequestsSucceeded"] else 1


def run_api_smoke(args):
    try:
        with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=15, trust_env=False) as client:
            health = client.get("/api/health")
            health.raise_for_status()
            if health.json()["provider"] != "ollama" or health.json()["is_mock"]:
                raise ValueError("This live check requires explicitly configured Ollama")
            official = client.get("/api/checklists/official")
            official.raise_for_status()
            checklist = official.json()
            if not args.full_checklist:
                response = client.get("/api/checklists/live-smoke")
                if response.status_code == 404:
                    response = client.post(
                        "/api/checklists",
                        json={"checklist_id": "live-smoke", "criteria": checklist["criteria"][:1]},
                    )
                response.raise_for_status()
                checklist = response.json()
            records = []
            for language, text in (
                ("RU", "Здравствуйте! Меня зовут Анна. Чем могу помочь?"),
                ("KZ", "Сәлеметсіз бе! Менің атым Анна. Қалай көмектесе аламын?"),
                ("EN", "Hello! My name is Anna. How can I help?"),
            ):
                records.append(
                    {
                        "conversation_id": "live-smoke-" + language.lower(),
                        "language": language,
                        "channel": "agent chat",
                        "transcript": [{"speaker": "operator", "timestamp": "00:01", "text": text}],
                    }
                )
            response = client.post(
                "/api/datasets/import",
                json={
                    "payload": {
                        "isSuccess": True,
                        "data": {
                            "dataset_group_id": "SYNTHETIC-LIVE",
                            "total_records": len(records),
                            "records": records,
                        },
                    }
                },
            )
            response.raise_for_status()
            for record in records:
                started = time.monotonic()
                response = client.post(
                    "/api/evaluations",
                    json={
                        "conversation_id": record["conversation_id"],
                        "checklist_id": checklist["checklist_id"],
                        "checklist_version": checklist["version"],
                        "force": True,
                    },
                )
                response.raise_for_status()
                job = response.json()
                while job["status"] not in ("completed", "failed"):
                    if time.monotonic() - started > args.timeout:
                        print(
                            json.dumps(
                                {
                                    "job_id": job["job_id"],
                                    "status": job["status"],
                                    "error": "Wait expired; inspect durable job",
                                }
                            )
                        )
                        return 1
                    time.sleep(0.2)
                    response = client.get("/api/evaluation-jobs/" + job["job_id"])
                    response.raise_for_status()
                    job = response.json()
                if job["status"] == "failed":
                    print(json.dumps({"job_id": job["job_id"], "error": job["error_message"]}))
                    return 1
                response = client.get("/api/evaluations/" + job["evaluation_id"])
                response.raise_for_status()
                evaluation = response.json()
                if evaluation["is_mock"]:
                    raise ValueError("Unexpected mock result")
                result = evaluation["result_json"]
                if len(result["findings"]) != len(checklist["criteria"]):
                    raise ValueError("Incomplete findings")
                print(
                    json.dumps(
                        {
                            "language": record["language"],
                            "model": evaluation["model_name"],
                            "evaluation_id": evaluation["evaluation_id"],
                            "is_mock": False,
                            "criteria": len(result["findings"]),
                            "score": result["score"],
                            "seconds": round(time.monotonic() - started, 3),
                            "calls": result["metadata"].get("calls", []),
                        }
                    ),
                    flush=True,
                )
        return 0
    except (httpx.HTTPError, KeyError, ValueError):
        print("Live smoke failed: check server configuration and durable job status")
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--full-checklist", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--conversation-id", default="synthetic-live-next-action")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("Timeout must be positive")
    return run_local_smoke(args) if args.output_dir else run_api_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
