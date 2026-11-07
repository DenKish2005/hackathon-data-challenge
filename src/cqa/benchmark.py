"""Compare exported AI results with separately provided ground truth, never train on it."""

import argparse
import json
from pathlib import Path


def compare(predictions, truth):
    if isinstance(predictions, dict):
        predictions = predictions["conversations"]
    predicted = {d.get("conversation_id", d.get("id")): d for d in predictions}
    if len(predicted) != len(predictions):
        raise ValueError("Duplicate prediction IDs")
    correct = total = 0
    errors = []
    by_criterion = {}
    for expected in truth:
        actual = predicted.get(expected["conversation_id"], {})
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
    return {
        "criterion_accuracy": correct / total if total else None,
        "correct": correct,
        "total": total,
        "by_criterion": by_criterion,
        "score_mae": sum(errors) / len(errors) if errors else None,
        "scored_dialogues": len(errors),
        "expected_dialogues": len(truth),
        "missing_dialogues": [
            d["conversation_id"] for d in truth if d["conversation_id"] not in predicted
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
                json.loads(Path(args.predictions).read_text()),
                json.loads(Path(args.ground_truth).read_text()),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
