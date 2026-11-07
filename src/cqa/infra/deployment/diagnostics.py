"""Read-only local diagnostics; never download models or send inference requests."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url


def resources():
    result = {
        "system_ram_used_bytes": None,
        "system_ram_total_bytes": None,
        "gpu_used_mib": None,
        "gpu_total_mib": None,
    }
    if os.name == "nt":
        import ctypes

        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total",
                    "available",
                    "page",
                    "available_page",
                    "virtual",
                    "available_virtual",
                    "extended",
                )
            ]

        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result.update(
                system_ram_used_bytes=memory.total - memory.available,
                system_ram_total_bytes=memory.total,
            )
    elif Path("/proc/meminfo").exists():
        values = {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
        }
        result.update(
            system_ram_total_bytes=values["MemTotal"],
            system_ram_used_bytes=values["MemTotal"] - values["MemAvailable"],
        )
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        pairs = [[int(x.strip()) for x in line.split(",")] for line in output.stdout.splitlines()]
        result.update(gpu_used_mib=sum(p[0] for p in pairs), gpu_total_mib=sum(p[1] for p in pairs))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return result


def doctor(settings):
    from cqa.infra.llm import build_provider

    build_provider(settings)  # Apply the same endpoint and external-data policy as the server.
    db_path = make_url(settings.database_url).database
    location = Path(db_path).resolve().parent if db_path else Path.cwd()
    while not location.exists():
        location = location.parent
    disk = shutil.disk_usage(location)
    checks = {
        "frontend_build": (Path(settings.frontend_dir) / "index.html").is_file(),
        "disk_free_bytes": disk.free,
        "disk_ok": disk.free >= 512 * 1024**2,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "resources": resources(),
        "model_status": "not_checked",
    }
    if settings.llm_provider == "mock":
        checks["model_status"] = "mock"
    elif settings.llm_provider == "ollama":
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get(settings.llm_base_url.rstrip("/") + "/api/tags")
                response.raise_for_status()
                names = [m["name"] for m in response.json()["models"]]
                checks["model_status"] = "ready" if settings.llm_model in names else "missing_model"
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            checks["model_status"] = "ollama_unavailable"
    checks["ready"] = (
        checks["frontend_build"]
        and checks["disk_ok"]
        and checks["model_status"] in ("ready", "mock")
    )
    print(json.dumps(checks, indent=2))
    return 0 if checks["ready"] else 1
