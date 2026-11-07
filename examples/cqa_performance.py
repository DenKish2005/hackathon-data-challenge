"""Synthetic-only live benchmark; starts an isolated server and reuses the batch CLI.

No model downloads, private data, paid APIs or semantic prompt changes.
Each invocation measures one explicit configuration. Repeat with other flags to compare.
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from cqa.backend.__main__ import evaluate
from cqa.infra.deployment.diagnostics import resources


def synthetic_payload(count):
    return {
        "isSuccess": True,
        "data": {
            "dataset_group_id": "SYNTHETIC-PERFORMANCE",
            "total_records": count,
            "records": [
                {
                    "conversation_id": f"perf-{i}",
                    "language": "RU",
                    "channel": "agent chat",
                    "transcript": [
                        {
                            "speaker": "operator",
                            "timestamp": "00:01",
                            "text": "Здравствуйте! Меня зовут Анна, компания Freedom Broker. "
                            "Чем могу помочь?",
                        },
                        {
                            "speaker": "client",
                            "timestamp": "00:02",
                            "text": "Спасибо, вопрос решён.",
                        },
                        {
                            "speaker": "operator",
                            "timestamp": "00:03",
                            "text": "Спасибо за обращение. До свидания!",
                        },
                    ],
                }
                for i in range(count)
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=int, default=16384)
    parser.add_argument("--output-limit", type=int, default=4096)
    parser.add_argument("--critic", action="store_true")
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--out", type=Path, default=Path(".runtime/performance"))
    args = parser.parse_args()
    if not 1 <= args.parallel <= 4 or not 1 <= args.count <= 65 or args.timeout <= 0:
        parser.error("Use parallel 1..4, count 1..65 and a positive timeout")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    directory = args.out.resolve() / stamp
    directory.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    config = {
        "model": args.model,
        "context": args.context,
        "output_limit": args.output_limit,
        "critic": args.critic,
        "parallel": args.parallel,
        "count": args.count,
        "fixture": "synthetic-three-message-ru-v1",
        "cold_model_forced": False,
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "cpu_count": os.cpu_count(),
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    config["git_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
    (directory / "configuration.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite:///" + str(directory / "benchmark.db"),
        "LLM_PROVIDER": "ollama",
        "LLM_BASE_URL": "http://127.0.0.1:11434",
        "LLM_MODEL": args.model,
        "LLM_CONTEXT_SIZE": str(args.context),
        "LLM_OUTPUT_LIMIT": str(args.output_limit),
        "LLM_TIMEOUT": str(args.timeout),
        "CQA_JOB_TIMEOUT": str(args.timeout),
        "LLM_ATTEMPTS": "1",
        "LLM_CONCURRENCY": str(args.parallel),
        "CQA_WORKERS": str(args.parallel),
        "CQA_ENABLE_CRITIC": str(args.critic).lower(),
        "PYTHONIOENCODING": "utf-8",
    }
    # The benchmark server must not read private organizer configuration from the caller.
    for key in (
        "FREEDOM_DATASET_URLS_FILE",
        "FREEDOM_DEV_API_URL",
        "FREEDOM_CONTROL_API_URL",
        "CQA_DATA_URL",
    ):
        env.pop(key, None)
    stop = threading.Event()
    samples = []

    def monitor():
        while not stop.is_set():
            samples.append({"seconds": round(time.monotonic() - started, 3), **resources()})
            stop.wait(2)

    started = time.monotonic()
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "cqa", "serve", "--port", str(port)],
            env=env,
            stdout=log,
            stderr=log,
        )
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        try:
            with httpx.Client(base_url=base, timeout=10, trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Benchmark server did not become ready")
                    try:
                        health = client.get("/api/health")
                        health.raise_for_status()
                        if health.json()["status"] != "ready":
                            raise RuntimeError("Local Ollama/model unavailable; nothing downloaded")
                        break
                    except httpx.HTTPError:
                        time.sleep(0.2)
                response = client.post(
                    "/api/datasets/import", json={"payload": synthetic_payload(args.count)}
                )
                response.raise_for_status()
            result = evaluate(
                SimpleNamespace(
                    api_url=base,
                    checklist_id="official",
                    version=1,
                    id=None,
                    group_id="SYNTHETIC-PERFORMANCE",
                    limit=None,
                    timeout=args.timeout + 30,
                    force=False,
                    retry_failed=False,
                    report=directory / "report.json",
                    failed_only=False,
                    parallel=args.parallel,
                )
            )
        finally:
            stop.set()
            monitor_thread.join(timeout=5)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            (directory / "resources.json").write_text(
                json.dumps(
                    {
                        "scope": "system RAM and total NVIDIA VRAM, sampled every ~2 seconds; "
                        "includes other apps",
                        "samples": samples,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    print(json.dumps({"directory": str(directory), "exit_code": result}), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
