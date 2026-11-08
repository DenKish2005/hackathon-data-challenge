import json
import os
import subprocess
import sys
from pathlib import Path


def test_launcher_preflight_reuses_explicit_python_without_starting_model(tmp_path):
    root = Path(__file__).resolve().parents[2]
    config = tmp_path / "demo.env"
    config.write_text("LLM_PROVIDER=mock\nLLM_CONTEXT_SIZE=32768\n", encoding="utf-8")
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "CQA_"))}
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/run-cqa.py"),
            "--check",
            "--env-file",
            str(config),
            "--python",
            sys.executable,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    settings = json.loads(result.stdout)
    assert settings["python_exists"]
    assert settings["python"] == sys.executable
    assert settings["model"] == "qwen3:4b-instruct"
    assert settings["provider"] == "mock"
    assert settings["context_size"] == 32768
    assert settings["critic_enabled"]
