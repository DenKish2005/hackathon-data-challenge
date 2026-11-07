"""Bounded local Foundation-pipeline runs and paired semantic metrics.

Cases, predictions, labels and reports must stay outside Git worktrees. The run
command never opens labels. Compare only after predictions have been frozen.
No model downloads, remote providers, fine tuning or automatic large sweeps.
"""

import argparse
import asyncio
import itertools
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from cqa.prompts import PIPELINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION, fingerprint
from cqa.service import EvaluationRequest, score


def private_path(value):
    path = Path(value).resolve()
    if any((parent / ".git").exists() for parent in [path, *path.parents]):
        raise ValueError("Benchmark inputs and outputs must be outside all Git worktrees")
    return path


def read_private(value):
    return json.loads(private_path(value).read_text(encoding="utf-8-sig"))


def write_new(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def load_cases(path):
    cases = read_private(path)["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Cases require unique nonempty IDs")
    result = []
    for case in cases:
        if set(case) - {"id", "request", "channel", "checklistId", "sections"}:
            raise ValueError("Case files must contain requests only, never expected labels")
        request = EvaluationRequest.model_validate(case["request"])
        content = {
            "request": request.model_dump(exclude={"force"}),
            "channel": case.get("channel", "agent chat"),
            "checklistId": case.get("checklistId", "benchmark"),
            "sections": case.get("sections", []),
        }
        result.append({"id": case["id"], **content, "inputFingerprint": fingerprint(content)})
    return result


def pipeline_inputs(case):
    request = EvaluationRequest.model_validate(case["request"])
    conversation = SimpleNamespace(
        conversation_id=request.conversation_id,
        language=request.language,
        channel=case["channel"],
        messages=[
            SimpleNamespace(message_id=m.id, speaker=m.role, text=m.text, timestamp_original=m.time)
            for m in request.messages
        ],
    )
    checklist = SimpleNamespace(
        checklist_id=case["checklistId"],
        version=request.version,
        sections=case["sections"],
        criteria=request.criteria,
    )
    return request, conversation, checklist


def output_record(case, result, *, repeat, seconds, calls, model, generation):
    return {
        "caseId": case["id"],
        "inputFingerprint": case["inputFingerprint"],
        "repeat": repeat,
        "status": "completed",
        "model": model,
        "generation": generation,
        "answers": [
            {"criterionId": f["criterion_id"], "answer": f["answer"]} for f in result["findings"]
        ],
        "score": result["score"],
        "critical": result["critical"],
        "calls": calls,
        "seconds": seconds,
        "result": result,
    }


def metrics(records, cases, truth):
    """Equal case weight for accuracy; repeats measured separately, never cached."""
    grouped = defaultdict(list)
    for record in records:
        grouped[record["caseId"]].append(record)
    by_criterion = defaultdict(lambda: {"correct": 0, "total": 0, "confusion": Counter()})
    na = Counter(tp=0, fp=0, fn=0, tn=0, missing=0)
    errors, consistency = [], {}
    for case in cases:
        cid = case["id"]
        req = EvaluationRequest.model_validate(case["request"])
        criteria = {c.id: c for c in req.criteria}
        runs = sorted(grouped[cid], key=lambda r: r["repeat"])
        first = runs[0] if runs else {}
        values = {r["criterionId"]: r["answer"] for r in first.get("answers", [])}
        expected = truth[cid]
        for item in expected:
            kid, answer = item["criterionId"], item["answer"]
            actual = values.get(kid)
            criterion = criteria[kid]
            definition = fingerprint(
                criterion.model_dump(
                    include={"title", "description", "type", "scale", "naAllowed", "naCondition"}
                )
            )
            row = by_criterion[kid + "@" + definition]
            row.update(criterionId=kid, title=criterion.title, definitionFingerprint=definition)
            row["correct"] += actual == answer
            row["total"] += 1
            row["confusion"][f"{answer!s} -> {actual!s}"] += 1
            if actual is None:
                na["missing"] += 1
            else:
                na[
                    {
                        (True, True): "tp",
                        (True, False): "fn",
                        (False, True): "fp",
                        (False, False): "tn",
                    }[answer == "N/A", actual == "N/A"]
                ] += 1
        if {r["criterionId"] for r in expected} != {c.id for c in req.criteria}:
            raise ValueError("Labels must cover exactly the active criteria for each compared case")
        # Validate labels before computing a reference score; never silently coerce decisions.
        for criterion in req.criteria:
            answer = next(r["answer"] for r in expected if r["criterionId"] == criterion.id)
            allowed = criterion.scale if criterion.type == "scale" else ["Да", "Нет"]
            if type(answer) is bool or answer not in [
                *allowed,
                *(["N/A"] if criterion.naAllowed else []),
            ]:
                raise ValueError("Label is outside its active rubric")
        expected_score = score(req.criteria, [SimpleNamespace(**r) for r in expected])["score"]
        if expected_score is not None and first.get("score") is not None:
            errors.append(abs(expected_score - first["score"]))
        successful = [r for r in runs if r["status"] == "completed"]
        pairs = list(itertools.combinations(successful, 2))
        agreements = []
        for left, right in pairs:
            a = {r["criterionId"]: r["answer"] for r in left["answers"]}
            b = {r["criterionId"]: r["answer"] for r in right["answers"]}
            agreements.append(sum(a[k] == b[k] for k in a) / len(a))
        scores = [r["score"] for r in successful if r["score"] is not None]
        consistency[cid] = {
            "attempts": len(runs),
            "completed": len(successful),
            "repeatPairs": len(pairs),
            "pairwiseCriterionAgreement": statistics.mean(agreements) if agreements else None,
            "scoreRange": max(scores) - min(scores) if len(scores) > 1 else None,
            "distinctAnswerSets": len(
                {
                    fingerprint(sorted(r["answers"], key=lambda v: v["criterionId"]))
                    for r in successful
                }
            ),
        }
    correct = sum(r["correct"] for r in by_criterion.values())
    total = sum(r["total"] for r in by_criterion.values())
    durations = [r["seconds"] for r in records]
    return {
        "criterionAccuracy": correct / total if total else None,
        "correct": correct,
        "total": total,
        "byCriterion": {
            k: {**r, "accuracy": r["correct"] / r["total"], "confusion": dict(r["confusion"])}
            for k, r in sorted(by_criterion.items())
        },
        "naConfusion": dict(na),
        "scoreMAE": statistics.mean(errors) if errors else None,
        "scorePairs": len(errors),
        "expectedCases": len(cases),
        "scoreCoverage": len(errors) / len(cases) if cases else None,
        "consistency": consistency,
        "modelCalls": sum(r["calls"] for r in records),
        "latency": {
            "totalSeconds": sum(durations),
            "medianSeconds": statistics.median(durations) if durations else None,
            "maxSeconds": max(durations) if durations else None,
        },
        "failures": sum(r["status"] != "completed" for r in records),
    }


def compare_runs(before, after, cases, labels):
    ids = {r["caseId"] for r in before} & {r["caseId"] for r in after}
    paired = [c for c in cases if c["id"] in ids]
    if not paired:
        raise ValueError("No paired cases")
    for case in paired:
        req = EvaluationRequest.model_validate(case["request"])
        criteria = {c.id: c for c in req.criteria}
        records = [r for r in [*before, *after] if r["caseId"] == case["id"]]
        if any(r["inputFingerprint"] != case["inputFingerprint"] for r in records):
            raise ValueError("Cannot compare different transcripts or checklist definitions")
        if (
            len({r["model"] for r in records}) != 1
            or len({fingerprint(r["generation"]) for r in records}) != 1
        ):
            raise ValueError("Paired comparison requires identical model and generation settings")
        for record in records:
            if record.get("cached") or record.get("is_mock"):
                raise ValueError("Cached or mocked results cannot measure fresh consistency")
            answers = record.get("answers", [])
            if len({r["criterionId"] for r in answers}) != len(answers):
                raise ValueError("Duplicate predicted criteria")
            if record["status"] == "completed":
                if {r["criterionId"] for r in answers} != set(criteria):
                    raise ValueError("Completed predictions must cover the active rubric")
                for item in answers:
                    c = criteria[item["criterionId"]]
                    allowed = c.scale if c.type == "scale" else ["Да", "Нет"]
                    answer = item["answer"]
                    if type(answer) is bool or answer not in [
                        *allowed,
                        *(["N/A"] if c.naAllowed else []),
                    ]:
                        raise ValueError("Prediction is outside its active rubric")
                if (
                    record["score"]
                    != score(criteria.values(), [SimpleNamespace(**r) for r in answers])["score"]
                ):
                    raise ValueError("Stored prediction score differs from deterministic rescoring")
            if (
                type(record["calls"]) is not int
                or record["calls"] < 0
                or type(record["seconds"]) not in (int, float)
                or not math.isfinite(record["seconds"])
                or record["seconds"] < 0
            ):
                raise ValueError("Invalid call/latency measurement")
        expected = labels[case["id"]]
        if len(expected) != len(criteria) or len({r["criterionId"] for r in expected}) != len(
            expected
        ):
            raise ValueError("Labels must contain exactly one answer per criterion")
        for variant in [before, after]:
            repeats = [r["repeat"] for r in variant if r["caseId"] == case["id"]]
            if len(set(repeats)) != len(repeats):
                raise ValueError("Duplicate repeat measurements")
    return {
        "pairedCases": [c["id"] for c in paired],
        "labelledCasesNotPaired": sorted(set(labels) - ids),
        "before": metrics([r for r in before if r["caseId"] in ids], paired, labels),
        "after": metrics([r for r in after if r["caseId"] in ids], paired, labels),
        "limits": (
            "Small diagnostic sample; first run per case measures accuracy, "
            "repeats measure consistency."
        ),
    }


async def run(args):
    from cqa.infra.llm.ollama import OllamaProvider
    from cqa.infra.orchestrator.pipeline import Pipeline, ProviderCritic, ProviderEvaluator

    endpoint = urlsplit(args.base_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Only loopback Ollama is allowed")
    if ":cloud" in args.model.lower() or args.model.lower().endswith("-cloud"):
        raise ValueError("Cloud models are not allowed")
    cases = load_cases(args.cases)
    if args.only:
        if not set(args.only) <= {c["id"] for c in cases}:
            raise ValueError("Unknown selected case")
        cases = [c for c in cases if c["id"] in args.only]
    if not 1 <= len(cases) <= args.max_cases <= 2:
        raise ValueError("Select at most two cases")
    if not 1 <= args.repeats <= 2 or not 1 <= args.max_evaluations <= 4:
        raise ValueError("At most two repeats and four evaluations are allowed")
    if not 1 <= args.max_model_calls <= 8 or not 0 < args.deadline_seconds <= 900:
        raise ValueError("At most eight generation calls and 900 seconds are allowed")
    output = private_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    provider = OllamaProvider(
        args.base_url,
        args.model,
        context_size=args.context_size,
        output_limit=args.output_limit,
        timeout=args.timeout,
        concurrency=1,
        attempts=1,
    )
    evaluator = ProviderEvaluator(provider)
    pipeline = Pipeline(evaluator, critic=ProviderCritic(evaluator))
    generation = {
        "temperature": 0,
        "contextSize": args.context_size,
        "outputLimit": args.output_limit,
    }
    generate = provider.generate
    count = 0
    records = []
    started = time.perf_counter()

    async def capture(messages, schema):
        nonlocal count
        if count >= args.max_model_calls:
            raise RuntimeError("Model-call budget exhausted")
        count += 1
        number = count
        write_new(
            output / f"calls/{number:02}-request.json", {"messages": messages, "schema": schema}
        )
        try:
            generated = await generate(messages, schema)
        except Exception as exc:
            write_new(
                output / f"calls/{number:02}-error.json",
                {
                    "errorType": type(exc).__name__,
                    "code": getattr(exc, "code", None),
                    "details": str(exc),
                    "cause": str(exc.__cause__) if exc.__cause__ else None,
                },
            )
            raise
        write_new(
            output / f"calls/{number:02}-response.json",
            {"value": generated, "metadata": generated.metadata},
        )
        return generated

    provider.generate = capture
    stop = False
    for repeat in range(args.repeats):
        for case in cases:
            if len(records) >= args.max_evaluations or stop:
                break
            before = count
            case_started = time.perf_counter()
            try:
                remaining = args.deadline_seconds - (case_started - started)
                if remaining <= 0 or count >= args.max_model_calls:
                    stop = True
                    break
                async with asyncio.timeout(remaining):
                    _, conversation, checklist = pipeline_inputs(case)
                    result = await pipeline.run(conversation, checklist)
                record = output_record(
                    case,
                    result,
                    repeat=repeat,
                    seconds=round(time.perf_counter() - case_started, 3),
                    calls=count - before,
                    model=args.model,
                    generation=generation,
                )
            except Exception as exc:
                record = {
                    "caseId": case["id"],
                    "inputFingerprint": case["inputFingerprint"],
                    "repeat": repeat,
                    "status": "failed",
                    "errorType": type(exc).__name__,
                    "model": args.model,
                    "generation": generation,
                    "calls": count - before,
                    "seconds": round(time.perf_counter() - case_started, 3),
                }
                stop = isinstance(exc, (TimeoutError, RuntimeError))
            records.append(record)
            write_new(output / f"evaluation-{len(records):02}.json", record)
            print(
                json.dumps({k: v for k, v in record.items() if k not in {"result", "answers"}}),
                flush=True,
            )
        if stop:
            break
    write_new(
        output / "predictions.json",
        {
            "versions": {
                "prompt": PROMPT_VERSION,
                "schema": SCHEMA_VERSION,
                "pipeline": PIPELINE_VERSION,
            },
            "records": records,
            "modelCalls": count,
            "wallSeconds": round(time.perf_counter() - started, 3),
        },
    )
    return 1 if any(r["status"] != "completed" for r in records) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run")
    live.add_argument("--cases", required=True)
    live.add_argument("--output-dir", required=True)
    live.add_argument("--only", nargs="+")
    live.add_argument("--base-url", default="http://127.0.0.1:11434")
    live.add_argument("--model", default="qwen3:4b-instruct")
    live.add_argument("--context-size", type=int, default=32768)
    live.add_argument("--output-limit", type=int, default=5000)
    live.add_argument("--timeout", type=float, default=300)
    live.add_argument("--repeats", type=int, default=1)
    live.add_argument("--max-cases", type=int, default=2)
    live.add_argument("--max-evaluations", type=int, default=3)
    live.add_argument("--max-model-calls", type=int, default=8)
    live.add_argument("--deadline-seconds", type=float, default=900)
    compare = sub.add_parser("compare")
    for name in ["before", "after", "cases", "labels", "output"]:
        compare.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if args.command == "run":
        return asyncio.run(run(args))
    report = compare_runs(
        read_private(args.before)["records"],
        read_private(args.after)["records"],
        load_cases(args.cases),
        read_private(args.labels),
    )
    write_new(args.output, report)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
