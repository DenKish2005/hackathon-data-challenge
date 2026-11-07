"""Run the frontend and stateful API together on Windows, Linux or macOS."""

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
KEYS = {
    "CQA_DATA_URL",
    "FREEDOM_DEV_API_URL",
    "FREEDOM_CONTROL_API_URL",
    "FREEDOM_DATASET_URLS_FILE",
    "DATABASE_URL",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "CQA_ALLOW_EXTERNAL_DATA",
    "CQA_STRATEGY",
    "CQA_AGENT_CONCURRENCY",
    "CQA_WORKERS",
    "CQA_JOB_TIMEOUT",
    "LLM_TIMEOUT",
    "LLM_CONCURRENCY",
    "LLM_ATTEMPTS",
    "LLM_CONTEXT_SIZE",
    "LLM_OUTPUT_LIMIT",
    "CQA_ENABLE_CRITIC",
}


def load_config(path):
    if not path.exists():
        return {}
    data = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key.strip() not in KEYS:
            raise ValueError(f"Invalid setting on line {number}; use .env.cqa.example")
        data[key.strip()] = value.strip().strip("\"'")
    return data


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.cqa")
    parser.add_argument("--configure-source", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    settings = load_config(args.env_file)
    if args.configure_source:
        source = getpass.getpass("Paste the organizer HTTPS URL (input hidden): ").strip()
        parts = urlsplit(source)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("A valid HTTPS source URL is required")
        settings["CQA_DATA_URL"] = source
        args.env_file.write_text(
            "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n", encoding="utf-8"
        )
        args.env_file.chmod(0o600)
        print("Source saved in the private local configuration.")
    environment = {**os.environ, **settings}
    environment.setdefault("LLM_PROVIDER", "ollama")
    environment.setdefault("LLM_BASE_URL", "http://127.0.0.1:11434")
    environment.setdefault("LLM_MODEL", "qwen3:4b")
    environment.setdefault("LLM_CONCURRENCY", "1")
    environment.setdefault("LLM_TIMEOUT", "600")
    environment.setdefault("CQA_JOB_TIMEOUT", "1800")
    environment.setdefault("LLM_CONTEXT_SIZE", "65536")
    environment.setdefault("LLM_OUTPUT_LIMIT", "4096")
    environment.setdefault("CQA_STRATEGY", "two_pass")
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if args.check:
        print(
            json.dumps(
                {
                    "project": str(ROOT),
                    "python": str(python),
                    "npm_available": bool(npm),
                    "frontend_built": (ROOT / "frontend/dist/index.html").exists(),
                    "source_configured": bool(
                        environment.get("CQA_DATA_URL") or environment.get("FREEDOM_DEV_API_URL")
                    ),
                    "provider": environment["LLM_PROVIDER"],
                    "model": environment["LLM_MODEL"],
                    "strategy": environment["CQA_STRATEGY"],
                    "local_url": f"http://{args.host}:{args.port}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if sys.version_info < (3, 11):  # noqa: UP036 -- standalone launcher precedes installation
        raise ValueError("Python 3.11 or newer is required")
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    dependencies = subprocess.run(
        [str(python), "-c", "import cqa, fastapi, uvicorn, httpx, sqlalchemy, openai"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
    )
    if dependencies.returncode:
        subprocess.run(
            [str(python), "-m", "pip", "install", "-e", "."], cwd=ROOT, env=environment, check=True
        )
    if not args.skip_build:
        if not npm:
            raise ValueError("Install Node.js LTS, reopen the terminal and retry")
        frontend = ROOT / "frontend"
        if not (frontend / "node_modules").exists():
            subprocess.run([npm, "ci"], cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    if not (ROOT / "frontend/dist/index.html").exists():
        raise ValueError("The frontend build is missing; rerun without --skip-build")
    print(f"Open http://{args.host}:{args.port} and leave this terminal running.", flush=True)
    print(
        "Provider: " + environment["LLM_PROVIDER"] + ". "
        "A real evaluation requires the configured model to be running.",
        flush=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "uvicorn",
            "cqa.api:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
