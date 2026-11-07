"""CLI: run the app, import unseen datasets, evaluate batches, export reports."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from cqa.service import EvaluationRequest, Evaluator, Store
from cqa.workspace import (
    WorkspaceConflict,
    default_checklist,
    normalize_records,
    read_workspace,
    write_workspace,
)


def load(store):
    workspace = read_workspace(store)
    if workspace["data"] is None:
        workspace["data"] = {
            "dialogs": [],
            "criteria": default_checklist(),
            "version": 1,
            "appeals": [],
        }
    return workspace


async def evaluate(args, store):
    workspace = load(store)
    data = workspace["data"]
    dialogs = [
        d
        for d in data["dialogs"]
        if (not args.id or d["id"] == args.id) and (d["status"] == "pending" or args.force)
    ]
    if args.limit:
        dialogs = dialogs[: args.limit]
    if not dialogs:
        raise ValueError("Нет подходящих диалогов. Используйте import или --force для переоценки")
    evaluator = Evaluator(store)
    failures = 0
    for i, d in enumerate(dialogs):
        print(f"[{i + 1}/{len(dialogs)}] {d['id']}: анализ…", flush=True)
        try:
            request = EvaluationRequest(
                conversation_id=d["id"],
                language=d["language"],
                messages=d["messages"],
                criteria=data["criteria"],
                version=data["version"],
                force=args.force,
            )
            result = await evaluator.evaluate(request)
            d.update(result, status="done", source="ollama", originalResults=result["results"])
            # Every successful result is durable; a crash does not lose the batch.
            saved = write_workspace(store, workspace["revision"], data)
            workspace["revision"] = saved["revision"]
            print(f"  {result['score']}/100; critical={result['critical']}", flush=True)
        except (httpx.HTTPError, ValueError) as exc:
            failures += 1
            print(f"  ERROR {type(exc).__name__}: {str(exc)[:250]}", file=sys.stderr, flush=True)
            if isinstance(exc, (httpx.ConnectError, WorkspaceConflict)):
                break
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
                break
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Freedom CQA — локальная оценка новых диалогов")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    importer = commands.add_parser("import")
    importer.add_argument("file")
    runner = commands.add_parser("evaluate")
    runner.add_argument("--id")
    runner.add_argument("--limit", type=int)
    runner.add_argument("--force", action="store_true")
    exporter = commands.add_parser("export")
    exporter.add_argument("file")
    args = parser.parse_args()
    if args.command == "evaluate" and args.limit is not None and args.limit <= 0:
        parser.error("--limit должен быть положительным")
    if args.command == "serve":
        import uvicorn

        uvicorn.run("cqa.api:app", host=args.host, port=args.port)
        return 0
    store = Store()
    if args.command == "evaluate":
        return asyncio.run(evaluate(args, store))
    workspace = load(store)
    data = workspace["data"]
    if args.command == "import":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        dialogs = normalize_records(payload, data["criteria"], data["version"], data["dialogs"])
        data["dialogs"].extend(dialogs)
        write_workspace(store, workspace["revision"], data)
        print(f"Импортировано {len(dialogs)} диалогов. Оценки отсутствуют до анализа моделью.")
    else:
        report = {**data, "conversations": data["dialogs"]}
        Path(args.file).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Экспортировано {len(data['dialogs'])} диалогов")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
