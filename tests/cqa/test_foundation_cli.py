import json
import os
import subprocess
import sys

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
