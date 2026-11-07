"""Explicit, synthetic-only live Ollama check against the running unified backend.

Run: python examples/cqa_live_smoke.py [--full-checklist] [--timeout 600]
No model download, API credentials, paid calls or private datasets are used.
"""

import argparse
import json
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--full-checklist", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("Timeout must be positive")
    try:
        with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=15, trust_env=False) as client:
            health = client.get("/api/health")
            health.raise_for_status()
            if health.json()["provider"] != "ollama" or health.json()["is_mock"]:
                raise ValueError("This live check requires explicitly configured Ollama")
            official = client.get("/api/checklists/official")
            official.raise_for_status()
            checklist = official.json()
            if not args.full_checklist:
                response = client.get("/api/checklists/live-smoke")
                if response.status_code == 404:
                    response = client.post(
                        "/api/checklists",
                        json={"checklist_id": "live-smoke", "criteria": checklist["criteria"][:1]},
                    )
                response.raise_for_status()
                checklist = response.json()
            records = []
            for language, text in (
                ("RU", "Здравствуйте! Меня зовут Анна. Чем могу помочь?"),
                ("KZ", "Сәлеметсіз бе! Менің атым Анна. Қалай көмектесе аламын?"),
                ("EN", "Hello! My name is Anna. How can I help?"),
            ):
                records.append(
                    {
                        "conversation_id": "live-smoke-" + language.lower(),
                        "language": language,
                        "channel": "agent chat",
                        "transcript": [{"speaker": "operator", "timestamp": "00:01", "text": text}],
                    }
                )
            response = client.post(
                "/api/datasets/import",
                json={
                    "payload": {
                        "isSuccess": True,
                        "data": {
                            "dataset_group_id": "SYNTHETIC-LIVE",
                            "total_records": len(records),
                            "records": records,
                        },
                    }
                },
            )
            response.raise_for_status()
            for record in records:
                started = time.monotonic()
                response = client.post(
                    "/api/evaluations",
                    json={
                        "conversation_id": record["conversation_id"],
                        "checklist_id": checklist["checklist_id"],
                        "checklist_version": checklist["version"],
                        "force": True,
                    },
                )
                response.raise_for_status()
                job = response.json()
                while job["status"] not in ("completed", "failed"):
                    if time.monotonic() - started > args.timeout:
                        print(
                            json.dumps(
                                {
                                    "job_id": job["job_id"],
                                    "status": job["status"],
                                    "error": "Wait expired; inspect durable job",
                                }
                            )
                        )
                        return 1
                    time.sleep(0.2)
                    response = client.get("/api/evaluation-jobs/" + job["job_id"])
                    response.raise_for_status()
                    job = response.json()
                if job["status"] == "failed":
                    print(json.dumps({"job_id": job["job_id"], "error": job["error_message"]}))
                    return 1
                response = client.get("/api/evaluations/" + job["evaluation_id"])
                response.raise_for_status()
                evaluation = response.json()
                if evaluation["is_mock"]:
                    raise ValueError("Unexpected mock result")
                result = evaluation["result_json"]
                if len(result["findings"]) != len(checklist["criteria"]):
                    raise ValueError("Incomplete findings")
                print(
                    json.dumps(
                        {
                            "language": record["language"],
                            "model": evaluation["model_name"],
                            "evaluation_id": evaluation["evaluation_id"],
                            "is_mock": False,
                            "criteria": len(result["findings"]),
                            "score": result["score"],
                            "seconds": round(time.monotonic() - started, 3),
                            "calls": result["metadata"].get("calls", []),
                        }
                    ),
                    flush=True,
                )
        return 0
    except (httpx.HTTPError, KeyError, ValueError):
        print("Live smoke failed: check server configuration and durable job status")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
