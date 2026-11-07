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
    """Submit bounded batches to the existing durable server queue."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    stop = Event()

    from cqa.backend.services.batch_report import save_report

    report_path = getattr(args, "report", None)
    previous = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if (report_path and report_path.exists() and getattr(args, "failed_only", False))
        else None
    )
    if getattr(args, "failed_only", False) and previous is None:
        raise ValueError("--failed-only requires an existing --report")
    started = time.monotonic()
    outputs = []
    interrupted = False
    with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=15, trust_env=False) as client:
        response = client.get(f"/api/checklists/{args.checklist_id}")
        response.raise_for_status()
        version = args.version or response.json()["version"]
        if previous and (previous["checklist_id"], previous["version"]) != (
            args.checklist_id,
            version,
        ):
            raise ValueError("Failed-only report must match the selected checklist version")
        if args.id:
            ids = [args.id]
        else:
            ids, offset = [], 0
            while True:
                params = {"offset": offset, "limit": 1000}
                if getattr(args, "group_id", None):
                    params["group_id"] = args.group_id
                response = client.get("/api/conversations", params=params)
                response.raise_for_status()
                batch = response.json()
                ids.extend(row["conversation_id"] for row in batch)
                if len(batch) < 1000:
                    break
                offset += len(batch)
        if previous:
            failed = {r["conversation_id"] for r in previous["results"] if r["status"] == "failed"}
            ids = [cid for cid in ids if cid in failed]
        if args.limit:
            ids = ids[: args.limit]

        def run_one(cid):
            output = {"conversation_id": cid, "status": "unavailable", "cached": False}
            began = time.monotonic()
            try:
                response = client.post(
                    "/api/evaluations",
                    json={
                        "conversation_id": cid,
                        "checklist_id": args.checklist_id,
                        "checklist_version": version,
                        "force": args.force,
                        "retry_failed": args.retry_failed or getattr(args, "failed_only", False),
                    },
                )
                response.raise_for_status()
                job = response.json()
                output["job_id"] = job["job_id"]
                output["cached"] = job["status"] == "completed"
                while job["status"] not in ("completed", "failed"):
                    if stop.is_set():
                        return {
                            **output,
                            "status": job["status"],
                            "error": "Polling interrupted; job remains durable",
                        }
                    if time.monotonic() - began >= args.timeout:
                        return {
                            **output,
                            "status": job["status"],
                            "error": "CLI wait expired; job remains durable",
                        }
                    time.sleep(0.2)
                    response = client.get("/api/evaluation-jobs/" + job["job_id"])
                    response.raise_for_status()
                    job = response.json()
                output.update(
                    status=job["status"],
                    evaluation_id=job.get("evaluation_id"),
                    metrics=job.get("metrics", []),
                )
                if job["status"] == "completed":
                    response = client.get("/api/evaluations/" + job["evaluation_id"])
                    response.raise_for_status()
                    output["score"] = response.json()["final_result_json"]["score"]
                else:
                    output["error"] = job["error_message"]
            except httpx.HTTPError:
                output["status"] = "unavailable"
                output["error"] = "Server unavailable; resubmit to recover durable job"
            output["wait_seconds"] = round(time.monotonic() - began, 6)
            return output

        workers = getattr(args, "parallel", 1)
        pool = ThreadPoolExecutor(max_workers=workers)
        pending = {}
        remaining = iter(ids)

        def fill():
            while len(pending) < workers:
                cid = next(remaining, None)
                if cid is None:
                    break
                pending[pool.submit(run_one, cid)] = cid

        try:
            from concurrent.futures import FIRST_COMPLETED, wait

            fill()
            while pending:
                done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    output = future.result()
                    outputs.append(output)
                    print(json.dumps(output), flush=True)
                    save_report(
                        report_path,
                        args.checklist_id,
                        version,
                        outputs,
                        time.monotonic() - started,
                        len(ids),
                    )
                    ok = sum(r["status"] == "completed" for r in outputs)
                    print(
                        f"Progress {len(outputs)}/{len(ids)}: success={ok} "
                        f"failed={len(outputs) - ok}",
                        file=sys.stderr,
                        flush=True,
                    )
                fill()
        except KeyboardInterrupt:
            interrupted = True
        finally:
            # Stop local polling promptly. Server jobs remain durable and recoverable.
            stop.set()
            pool.shutdown(wait=True, cancel_futures=True)
            for future in pending:
                if not future.cancelled():
                    outputs.append(future.result())
            save_report(
                report_path,
                args.checklist_id,
                version,
                outputs,
                time.monotonic() - started,
                len(ids),
                interrupted,
            )
    return 130 if interrupted else int(any(r["status"] != "completed" for r in outputs))


def main():
    parser = argparse.ArgumentParser(description="Freedom CQA unified backend")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    importer = commands.add_parser("import")
    importer.add_argument("file", type=Path, nargs="?")
    importer.add_argument("--organizer", metavar="GROUP_ID")
    exporter = commands.add_parser("export")
    exporter.add_argument("file", type=Path)
    runner = commands.add_parser("evaluate")
    runner.add_argument("--api-url", default="http://127.0.0.1:8000")
    runner.add_argument("--id")
    runner.add_argument("--group-id")
    runner.add_argument("--parallel", type=int, default=1)
    runner.add_argument("--report", type=Path)
    runner.add_argument("--failed-only", action="store_true")
    runner.add_argument("--limit", type=int)
    runner.add_argument("--checklist-id", default="official")
    runner.add_argument("--version", type=int)
    runner.add_argument("--force", action="store_true")
    runner.add_argument("--retry-failed", action="store_true")
    runner.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    if args.command == "import" and bool(args.file) == bool(args.organizer):
        parser.error("Select one local file or --organizer GROUP_ID")
    if args.command == "evaluate" and (
        not 1 <= args.parallel <= 16
        or args.failed_only
        and args.force
        or args.timeout <= 0
        or (args.limit is not None and args.limit <= 0)
        or (args.version is not None and args.version <= 0)
    ):
        parser.error(
            "Use positive timeout/limit/version, parallel 1..16, and no --force with --failed-only"
        )
    if args.command == "serve":
        import uvicorn

        uvicorn.run("cqa.backend.main:app", host=args.host, port=args.port, workers=1)
        return 0
    db = None
    try:
        if args.command == "doctor":
            from cqa.infra.deployment.diagnostics import doctor

            return doctor(Settings())
        if args.command == "evaluate":
            return evaluate(args)
        db = Database(Settings().database_url)
        db.initialize()
        seed_checklist(db)
        if args.command == "import":
            if args.organizer:
                import asyncio

                from cqa.backend.services.dataset_importer import fetch_organizer

                envelope = asyncio.run(fetch_organizer(Settings(), args.organizer))
            else:
                envelope = load_dataset(args.file)
            result = import_dataset(db, envelope)
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
    except (httpx.HTTPError, OSError, ValueError, RuntimeError):
        print("Command failed: check server, local file and configuration", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
