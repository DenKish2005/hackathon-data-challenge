"""Compare exported AI results with separately provided ground truth, never train on it."""

import argparse
import json
import math
from pathlib import Path


def _records(value):
    if isinstance(value, dict):
        value = value["conversations"]
    if not isinstance(value, list):
        raise ValueError("Expected a list of conversations")
    indexed = {}
    for item in value:
        identifier = item.get("conversation_id", item.get("id"))
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("Every conversation needs a nonempty string ID")
        if identifier in indexed:
            raise ValueError("Duplicate conversation IDs")
        results = item.get("results", [])
        ids = [r["criterionId"] for r in results]
        if any(not isinstance(cid, str) or not cid.strip() for cid in ids):
            raise ValueError("Criterion IDs must be nonempty strings")
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate criterion IDs")
        for result in results:
            answer = result["answer"]
            if isinstance(answer, bool) or not (
                answer in ("Да", "Нет", "N/A")
                or isinstance(answer, (int, float))
                and math.isfinite(answer)
            ):
                raise ValueError("Invalid criterion answer")
        score = item.get("score")
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 100
        ):
            raise ValueError("Score must be finite and between 0 and 100")
        indexed[identifier] = item
    return indexed


def compare(predictions, truth):
    predicted = _records(predictions)
    expected_records = _records(truth)
    if not expected_records or any(not item.get("results") for item in expected_records.values()):
        raise ValueError("Ground truth must include nonempty criterion results")
    correct = total = 0
    errors = []
    by_criterion = {}
    for identifier, expected in expected_records.items():
        actual = predicted.get(identifier, {})
        values = {r["criterionId"]: r["answer"] for r in actual.get("results", [])}
        for r in expected["results"]:
            cid = r["criterionId"]
            hit = values.get(cid) == r["answer"]
            correct += hit
            total += 1
            counts = by_criterion.setdefault(cid, {"correct": 0, "total": 0})
            counts["correct"] += hit
            counts["total"] += 1
        if expected.get("score") is not None and actual.get("score") is not None:
            errors.append(abs(expected["score"] - actual["score"]))
    expected_scores = sum(item.get("score") is not None for item in expected_records.values())
    return {
        "criterion_accuracy": correct / total,
        "correct": correct,
        "total": total,
        "by_criterion": by_criterion,
        # MAE is only defined for present score pairs; expose coverage next to it so
        # omitted low-quality predictions cannot masquerade as full-dataset quality.
        "score_mae": sum(errors) / len(errors) if errors else None,
        "score_coverage": len(errors) / expected_scores if expected_scores else None,
        "scored_dialogues": len(errors),
        "expected_scored_dialogues": expected_scores,
        "expected_dialogues": len(expected_records),
        "missing_dialogues": [
            identifier for identifier in expected_records if identifier not in predicted
        ],
        "missing_scores": [
            identifier
            for identifier, item in expected_records.items()
            if item.get("score") is not None and predicted.get(identifier, {}).get("score") is None
        ],
        "extra_dialogues": [
            identifier for identifier in predicted if identifier not in expected_records
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("predictions")
    p.add_argument("ground_truth")
    args = p.parse_args()
    print(
        json.dumps(
            compare(
                json.loads(Path(args.predictions).read_text(encoding="utf-8")),
                json.loads(Path(args.ground_truth).read_text(encoding="utf-8")),
            ),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
