"""Payload-free, atomically replaced reports for CLI and synthetic benchmarks."""

import csv
import json
from collections import Counter
from pathlib import Path


def summarize(results, elapsed, total):
    fresh = [r for r in results if r["status"] == "completed" and not r.get("cached")]
    completed = sum(r["status"] == "completed" for r in results)
    rate = len(fresh) / elapsed if elapsed > 0 and fresh else None
    calls = [c for r in results for m in r.get("metrics", []) for c in m.get("calls", [])]
    usage = {}
    for key in ("input_tokens", "output_tokens"):
        values = [c.get("usage", {}).get(key) for c in calls]
        usage[key] = sum(values) if values and all(v is not None for v in values) else None
    return {
        "selected": total,
        "reported": len(results),
        "completed": completed,
        "failed": sum(r["status"] == "failed" for r in results),
        "unfinished": total - completed - sum(r["status"] == "failed" for r in results),
        "cached": sum(bool(r.get("cached")) for r in results),
        "success_rate": completed / len(results) if results else None,
        "elapsed_seconds": round(elapsed, 6),
        "fresh_jobs_per_minute": rate * 60 if rate else None,
        "estimated_65_seconds": 65 / rate if rate else None,
        "llm_calls": len(calls),
        "http_attempts": sum(c.get("http_attempts", 0) for c in calls),
        "retries": sum(c.get("retries", 0) for c in calls),
        "invalid_responses": sum(
            c.get("error_code") in ("invalid_json", "invalid_output") for c in calls
        )
        + sum(
            m.get("error_code") == "validation_error" for r in results for m in r.get("metrics", [])
        ),
        "failure_reasons": dict(
            Counter(
                m.get("error_code", "unknown")
                for r in results
                for m in r.get("metrics", [])
                if m.get("status") == "failed"
            )
        ),
        **usage,
    }


def save_report(path, checklist_id, version, results, elapsed, total, interrupted=False):
    report = {
        "checklist_id": checklist_id,
        "version": version,
        "interrupted": interrupted,
        "summary": summarize(results, elapsed, total),
        "results": results,
    }
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        temp.replace(path)
        csv_path = path.with_suffix(".csv")
        temp = csv_path.with_suffix(".csv.tmp")
        fields = [
            "conversation_id",
            "job_id",
            "status",
            "evaluation_id",
            "cached",
            "score",
            "wait_seconds",
            "error",
        ]
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        temp.replace(csv_path)
    return report
