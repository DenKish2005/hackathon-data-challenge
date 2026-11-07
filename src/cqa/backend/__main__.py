"""All CLI entry points use the same Foundation store and HTTP job queue."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from cqa.backend.compat import workspace_view
from cqa.backend.config import Settings
from cqa.backend.database import Database
from cqa.backend.schemas import DatasetEnvelope
from cqa.backend.services.checklist_service import seed_checklist
from cqa.backend.services.dataset_importer import Conflict, import_dataset


def load_dataset(path):
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        payload = {
            "isSuccess": True,
            "data": {
                "dataset_group_id": "LOCAL",
                "total_records": len(payload),
                "records": payload,
            },
        }
    return DatasetEnvelope.model_validate(payload)


def evaluate(args):
    """Use the running server's configured provider; never start a competing worker."""
    failures = 0
    with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=15, trust_env=False) as client:
        response = client.get(f"/api/checklists/{args.checklist_id}")
        response.raise_for_status()
        version = args.version or response.json()["version"]
        if args.id:
            ids = [args.id]
        else:
            ids = []
            offset = 0
            while True:
                response = client.get(
                    "/api/conversations", params={"offset": offset, "limit": 1000}
                )
                response.raise_for_status()
                batch = response.json()
                ids.extend(row["conversation_id"] for row in batch)
                if len(batch) < 1000:
                    break
                offset += len(batch)
        if args.limit:
            ids = ids[: args.limit]
        for cid in ids:
            response = client.post(
                "/api/evaluations",
                json={
                    "conversation_id": cid,
                    "checklist_id": args.checklist_id,
                    "checklist_version": version,
                    "force": args.force,
                    "retry_failed": args.retry_failed,
                },
            )
            response.raise_for_status()
            job = response.json()
            deadline = time.monotonic() + args.timeout
            while job["status"] not in ("completed", "failed"):
                if time.monotonic() >= deadline:
                    print(
                        json.dumps(
                            {
                                "job_id": job["job_id"],
                                "status": job["status"],
                                "error": "CLI wait expired; job remains durable",
                            }
                        ),
                        flush=True,
                    )
                    return 1
                time.sleep(0.2)
                response = client.get("/api/evaluation-jobs/" + job["job_id"])
                response.raise_for_status()
                job = response.json()
            output = {
                "job_id": job["job_id"],
                "status": job["status"],
                "evaluation_id": job["evaluation_id"],
            }
            if job["status"] == "completed":
                response = client.get("/api/evaluations/" + job["evaluation_id"])
                response.raise_for_status()
                output["score"] = response.json()["final_result_json"]["score"]
            else:
                failures += 1
                output["error"] = job["error_message"]
            print(json.dumps(output), flush=True)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Freedom CQA unified backend")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    importer = commands.add_parser("import")
    importer.add_argument("file", type=Path)
    exporter = commands.add_parser("export")
    exporter.add_argument("file", type=Path)
    runner = commands.add_parser("evaluate")
    runner.add_argument("--api-url", default="http://127.0.0.1:8000")
    runner.add_argument("--id")
    runner.add_argument("--limit", type=int)
    runner.add_argument("--checklist-id", default="official")
    runner.add_argument("--version", type=int)
    runner.add_argument("--force", action="store_true")
    runner.add_argument("--retry-failed", action="store_true")
    runner.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    if args.command == "evaluate" and (
        args.timeout <= 0
        or (args.limit is not None and args.limit <= 0)
        or (args.version is not None and args.version <= 0)
    ):
        parser.error("Timeout, limit and version must be positive")
    if args.command == "serve":
        import uvicorn

        uvicorn.run("cqa.backend.main:app", host=args.host, port=args.port, workers=1)
        return 0
    db = None
    try:
        if args.command == "evaluate":
            return evaluate(args)
        db = Database(Settings().database_url)
        db.initialize()
        seed_checklist(db)
        if args.command == "import":
            result = import_dataset(db, load_dataset(args.file))
            print(result.model_dump_json())
        else:
            data = workspace_view(db)["data"] or {"dialogs": [], "appeals": []}
            args.file.write_text(
                json.dumps(
                    {**data, "conversations": data["dialogs"]}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
            print(json.dumps({"exported": len(data["dialogs"])}))
        return 0
    except Conflict:
        print("Import conflict: existing ID has different source data", file=sys.stderr)
        return 1
    except (httpx.HTTPError, OSError, ValueError):
        print("Command failed: check server, local file and configuration", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
