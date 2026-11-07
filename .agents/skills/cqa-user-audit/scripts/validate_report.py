#!/usr/bin/env python3
"""Validate a CQA user-audit run directory; never upload or print source data."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

SEVERITIES = {"BLOCKER", "CRITICAL", "MAJOR", "MINOR", "COSMETIC"}
PRIORITIES = {"P0", "P1", "P2"}
STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
VERDICTS = STATUSES
REQUIRED = ("REPORT.md", "BUGS.json", "ACTION_TRACE.jsonl", "COVERAGE.csv", "FIX_PROMPT.md")
SECRET_PATTERNS = (
    re.compile(r"(?:^|[?&])sig=[A-Za-z0-9_\-]{18,}", re.I | re.M),
    re.compile(r"(?i)(?:api[_\-]?key|authorization|bearer)\s*[:=]\s*[\"']?(?:sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_\-]{36,})"),
)


def validate(run: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not run.is_dir():
        return [f"Run directory not found: {run}"], warnings
    for name in REQUIRED:
        if not (run / name).is_file():
            errors.append(f"Missing {name}")
    if errors:
        return errors, warnings

    json_path = run / "BUGS.json"
    try:
        doc = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"BUGS.json invalid: {exc}"], warnings
    if not isinstance(doc, dict) or not isinstance(doc.get("bugs"), list):
        return ["BUGS.json must be an object with a bugs array"], warnings
    if not isinstance(doc.get("run"), dict):
        errors.append("BUGS.json must have a run object")
    ids: set[str] = set()
    bugs_by_id: dict[str, dict] = {}
    required_bug = ("id", "title", "severity", "priority", "steps", "expected", "actual", "scenario_ids", "evidence", "root_cause_hypothesis", "hypothesis_confidence")
    for i, bug in enumerate(doc["bugs"]):
        if not isinstance(bug, dict):
            errors.append(f"bugs[{i}]: not an object")
            continue
        bid = bug.get("id")
        if not isinstance(bid, str) or not re.fullmatch(r"CQA-BUG-\d{3,}", bid):
            errors.append(f"bugs[{i}]: invalid id")
        elif bid in ids:
            errors.append(f"bugs[{i}]: duplicate id {bid}")
        else:
            ids.add(bid)
            bugs_by_id[bid] = bug
        for key in required_bug:
            if key not in bug or bug[key] is None:
                errors.append(f"{bid or i}: missing {key}")
        if bug.get("severity") not in SEVERITIES:
            errors.append(f"{bid or i}: invalid severity")
        if bug.get("priority") not in PRIORITIES:
            errors.append(f"{bid or i}: invalid priority")
        if bug.get("hypothesis_confidence") not in {"low", "medium", "high"}:
            errors.append(f"{bid or i}: invalid hypothesis_confidence")
        if not isinstance(bug.get("steps"), list) or not bug.get("steps"):
            errors.append(f"{bid or i}: reproduction steps must be nonempty array")
        if not isinstance(bug.get("scenario_ids"), list) or not bug.get("scenario_ids"):
            errors.append(f"{bid or i}: scenario_ids must be nonempty array")
        for ev in bug.get("evidence", []):
            if not isinstance(ev, str):
                errors.append(f"{bid or i}: invalid evidence path")
                continue
            resolved = (run / ev).resolve()
            if not resolved.is_relative_to(run.resolve()) or not resolved.is_file():
                errors.append(f"{bid or i}: missing/unsafe evidence {ev}")

    scenario_rows = {}
    with (run / "COVERAGE.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required_cols = {"scenario_id", "priority", "category", "mode", "status", "executed_at", "notes", "bug_ids", "evidence"}
        if not required_cols.issubset(reader.fieldnames or []):
            errors.append("COVERAGE.csv missing required columns")
        else:
            for line_num, row in enumerate(reader, start=2):
                sid = row["scenario_id"]
                if not sid:
                    errors.append(f"COVERAGE.csv:{line_num}: missing scenario_id")
                    continue
                if sid in scenario_rows:
                    errors.append(f"COVERAGE.csv:{line_num}: duplicate {sid}")
                scenario_rows[sid] = row
                if row["status"] not in STATUSES:
                    errors.append(f"COVERAGE.csv:{line_num}: bad status {row['status']}")
                if row["priority"] not in PRIORITIES:
                    errors.append(f"COVERAGE.csv:{line_num}: bad priority")
                if row["status"] == "FAIL" and not row["bug_ids"].strip():
                    warnings.append(f"{sid}: FAIL should link to a bug or explain why in notes")
                for bid in (item.strip() for item in row["bug_ids"].split(";") if item.strip()):
                    if bid not in ids:
                        errors.append(f"{sid}: unknown bug reference {bid}")

    matrix = Path(__file__).resolve().parent.parent / "references" / "test-matrix.md"
    if matrix.is_file():
        defined = set(re.findall(r"^\|\s*((?:BOOT|DATA|NAV|EVAL|PROOF|RULE|APPEAL|AUDIO|NET|REL|EXP)-\d+)\s*\|", matrix.read_text(encoding="utf-8"), flags=re.M))
        missing = defined - set(scenario_rows)
        if missing:
            errors.append(f"COVERAGE.csv missing {len(missing)} matrix IDs, e.g. {', '.join(sorted(missing)[:12])}")
    if not scenario_rows:
        errors.append("COVERAGE.csv contains no scenarios")
    if scenario_rows and all(row["status"] == "NOT_RUN" for row in scenario_rows.values()):
        warnings.append("Every scenario NOT_RUN: report is structured but no user testing took place")

    trace = []
    for line_num, line in enumerate((run / "ACTION_TRACE.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"ACTION_TRACE.jsonl:{line_num}: malformed JSON")
            continue
        if not isinstance(item, dict):
            errors.append(f"ACTION_TRACE.jsonl:{line_num}: not an object")
            continue
        for key in ("step", "at", "scenario_id", "action", "expected", "observed", "verdict"):
            if key not in item:
                errors.append(f"ACTION_TRACE.jsonl:{line_num}: missing {key}")
        if item.get("verdict") not in VERDICTS:
            errors.append(f"ACTION_TRACE.jsonl:{line_num}: invalid verdict")
        for bid in item.get("bug_ids", []):
            if bid not in ids:
                errors.append(f"ACTION_TRACE.jsonl:{line_num}: unknown bug {bid}")
        trace.append(item)
    nums = [i.get("step") for i in trace]
    if any(not isinstance(n, int) for n in nums) or nums != sorted(set(nums)):
        errors.append("ACTION_TRACE step IDs must be strictly increasing unique integers")
    if not trace:
        warnings.append("No browser action trace entries: execution likely blocked or unperformed")
    for bid, bug in bugs_by_id.items():
        for sid in bug.get("scenario_ids", []):
            if sid not in scenario_rows:
                errors.append(f"{bid}: no coverage row for {sid}")

    for name in REQUIRED:
        value = (run / name).read_text(encoding="utf-8")
        if any(rx.search(value) for rx in SECRET_PATTERNS):
            errors.append(f"{name}: possible embedded signed URL or secret; REDACT before sharing")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    errors, warnings = validate(args.run_dir)
    for s in warnings:
        print(f"WARNING: {s}")
    if errors:
        for s in errors:
            print(f"ERROR: {s}")
        print(f"Audit package validation FAILED: {len(errors)} error(s).")
        return 1
    print("Audit package structure VALID. This does not certify test coverage or application quality.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
