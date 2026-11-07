import json
import subprocess
import sys

import pytest

from cqa.backend.compat import workspace_view
from cqa.backend.database import Database
from cqa.service import Store
from cqa.workspace import default_checklist, normalize_records, read_workspace, write_workspace


def record(cid="unseen"):
    return {
        "conversation_id": cid,
        "language": "EN",
        "channel": "agent chat",
        "transcript": [{"speaker": "operator", "timestamp": "00:01", "text": "Hello, I'm Alex."}],
    }


def test_import_normalization_and_duplicates():
    criteria = default_checklist()
    dialogs = normalize_records({"data": {"records": [record()]}}, criteria, 1)
    assert dialogs[0]["messages"][0]["time"] == "00:01"
    assert dialogs[0]["status"] == "pending"
    assert dialogs[0]["score"] is None
    with pytest.raises(ValueError):
        normalize_records([record()], criteria, 1, dialogs)
    with pytest.raises(ValueError):
        normalize_records([record(), record()], criteria, 1)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"data": None},
        [None],
        [dict(record(), transcript=None)],
        [dict(record(), transcript=["invalid"])],
        [dict(record(), conversation_id=[])],
        [dict(record(), audio_url="javascript:alert(1)")],
    ],
)
def test_bad_inputs_fail_explicitly(payload):
    with pytest.raises(ValueError):
        normalize_records(payload, default_checklist(), 1)


def test_cli_import_and_export_are_durable(tmp_path, monkeypatch):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([record()]))
    db = tmp_path / "db.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    subprocess.run([sys.executable, "-m", "cqa", "import", str(path)], check=True)
    database = Database(f"sqlite:///{db}")
    assert len(workspace_view(database)["data"]["dialogs"]) == 1
    output = tmp_path / "report.json"
    subprocess.run([sys.executable, "-m", "cqa", "export", str(output)], check=True)
    assert json.loads(output.read_text(encoding="utf-8"))["conversations"][0]["score"] is None
    repeated = subprocess.run([sys.executable, "-m", "cqa", "import", str(path)], check=False)
    assert repeated.returncode == 0
    assert len(workspace_view(database)["data"]["dialogs"]) == 1
    database.engine.dispose()


def test_cli_refuses_to_overwrite_browser_changes(tmp_path):
    store = Store(str(tmp_path / "db"))
    data = {"dialogs": [], "criteria": default_checklist(), "version": 1, "appeals": []}
    write_workspace(store, 0, data)
    with pytest.raises(ValueError):
        write_workspace(store, 0, {**data, "version": 2})
    assert read_workspace(store)["data"]["version"] == 1
