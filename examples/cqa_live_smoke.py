"""Explicit real-Ollama API acceptance run on synthetic examples; private outputs only."""

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--conversation-id", default="synthetic-live-next-action")
    args = parser.parse_args()
    from cqa.private_benchmark import private_path, write_new

    output = private_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CQA_DB"] = str(output / "app.sqlite3")
    os.environ.setdefault("CQA_MODEL", "qwen3:4b-instruct")
    os.environ.setdefault("CQA_NUM_CTX", "16384")
    os.environ.setdefault("CQA_NUM_PREDICT", "2000")
    endpoint = urlsplit(os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    model_name = os.environ["CQA_MODEL"].lower()
    if (
        endpoint.hostname not in ("127.0.0.1", "localhost", "::1")
        or ":cloud" in model_name
        or model_name.endswith("-cloud")
    ):
        parser.error("This real-data acceptance tool permits only local Ollama models")
    from fastapi.testclient import TestClient

    from cqa import api
    from cqa.service import ModelOutputError
    from cqa.workspace import normalize_records

    source = Path(__file__).resolve().parent
    criteria = json.loads((source / "cqa_replacement_checklist.json").read_text(encoding="utf-8"))
    records = json.loads((source / "cqa_synthetic.json").read_text(encoding="utf-8"))
    dialogs = normalize_records(records, criteria, 1)
    dialog = next((d for d in dialogs if d["id"] == args.conversation_id), None)
    if dialog is None:
        parser.error("Unknown synthetic conversation ID")
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
    generate = api.evaluator.generate
    calls = 0

    async def capture(messages, **kwargs):
        nonlocal calls
        calls += 1
        try:
            response = await generate(messages, **kwargs)
        except ModelOutputError as exc:
            write_new(output / "provider-responses" / f"{calls:04}.json", exc.response)
            raise
        write_new(output / "provider-responses" / f"{calls:04}.json", response)
        return response

    api.evaluator.generate = capture
    outcomes = []
    with TestClient(api.app) as client:
        for name, request in [
            ("new", payload),
            ("cached", payload),
            ("changed", changed),
            ("fresh", {**payload, "force": True}),
        ]:
            before = calls
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
                        "seconds": result.get("durationSeconds"),
                    }
                ),
                flush=True,
            )
    write_new(output / "api-results.json", outcomes)
    restart_code = (
        "import json; from fastapi.testclient import TestClient; from cqa.api import app; "
        "c=TestClient(app); print(json.dumps([r['evaluationId'] for r in "
        f"c.get({'/api/history/' + quote(dialog['id'], safe='')!r}).json()]))"
    )
    history = json.loads(subprocess.check_output([sys.executable, "-c", restart_code], text=True))
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


if __name__ == "__main__":
    raise SystemExit(main())
