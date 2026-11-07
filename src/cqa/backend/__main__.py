"""Standalone foundation CLI. Local import never needs an organizer/API credential."""

import argparse
import json
import sys
from pathlib import Path

from cqa.backend.config import Settings
from cqa.backend.database import Database
from cqa.backend.schemas import DatasetEnvelope
from cqa.backend.services.dataset_importer import Conflict, import_dataset


def main():
    parser = argparse.ArgumentParser(description="CQA Backend Foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    importer = commands.add_parser("import")
    importer.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("cqa.backend.main:app", host=args.host, port=args.port, workers=1)
        return 0
    db = None
    try:
        payload = DatasetEnvelope.model_validate(
            json.loads(args.file.read_text(encoding="utf-8-sig"))
        )
        db = Database(Settings().database_url)
        db.initialize()
        result = import_dataset(db, payload)
        print(result.model_dump_json())
        return 0
    except Conflict:
        print("Import conflict: existing ID has different source data", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Import failed: check local file format and access", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
