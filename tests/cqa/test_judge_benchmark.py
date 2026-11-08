import copy
import json
from types import SimpleNamespace

import pytest

from cqa.judge_benchmark import compare_runs, load_cases, private_path, run
from cqa.prompts import fingerprint
from cqa.service import score

from .test_evaluation import analysis, request


def cases():
    content = {
        "request": request().model_dump(exclude={"force"}),
        "channel": "agent chat",
        "checklistId": "benchmark",
        "sections": [],
    }
    return [{"id": "case", **content, "inputFingerprint": fingerprint(content)}]


def prediction(repeat=0):
    req = request()
    findings = analysis().results
    return {
        "caseId": "case",
        "inputFingerprint": cases()[0]["inputFingerprint"],
        "repeat": repeat,
        "model": "synthetic-local",
        "generation": {"temperature": 0},
        "status": "completed",
        "answers": [{"criterionId": r.criterionId, "answer": r.answer} for r in findings],
        "score": score(req.criteria, findings)["score"],
        "calls": 2,
        "seconds": 3.0,
    }


def test_metrics_separate_case_accuracy_na_errors_and_fresh_repeat_consistency():
    before = [prediction(0), prediction(1)]
    after = copy.deepcopy(before)
    after[0]["answers"][2]["answer"] = "Нет"
    after[0]["score"] = score(
        request().criteria, [SimpleNamespace(**r) for r in after[0]["answers"]]
    )["score"]
    labels = {"case": prediction()["answers"]}
    report = compare_runs(before, after, cases(), labels)
    assert report["before"]["criterionAccuracy"] == 1
    assert report["after"]["criterionAccuracy"] == 0.75
    assert report["after"]["naConfusion"] == {"tp": 0, "fp": 0, "fn": 1, "tn": 3, "missing": 0}
    assert report["after"]["consistency"]["case"]["pairwiseCriterionAgreement"] == 0.75
    assert report["after"]["consistency"]["case"]["scoreRange"] > 0
    assert report["after"]["scoreMAE"] > 0
    assert report["after"]["modelCalls"] == 4


@pytest.mark.parametrize(
    "change", ["input", "model", "settings", "cached", "mocked", "duplicate", "score"]
)
def test_comparison_rejects_unmatched_or_invalid_measurements(change):
    before, after = [prediction()], [prediction()]
    if change == "input":
        after[0]["inputFingerprint"] = "changed"
    if change == "model":
        after[0]["model"] = "different-model"
    if change == "settings":
        after[0]["generation"] = {"temperature": 1}
    if change == "cached":
        after[0]["cached"] = True
    if change == "mocked":
        after[0]["is_mock"] = True
    if change == "duplicate":
        after[0]["answers"].append(after[0]["answers"][0])
    if change == "score":
        after[0]["score"] = 999
    with pytest.raises(ValueError):
        compare_runs(before, after, cases(), {"case": prediction()["answers"]})


def test_failed_repeat_is_visible_in_accuracy_and_score_coverage():
    failed = {**prediction(), "status": "failed"}
    failed.pop("answers")
    failed.pop("score")
    report = compare_runs([prediction()], [failed], cases(), {"case": prediction()["answers"]})
    assert report["after"]["correct"] == 0
    assert report["after"]["scoreCoverage"] == 0
    assert report["after"]["naConfusion"]["missing"] == 4
    assert report["after"]["failures"] == 1
    assert report["after"]["consistency"]["case"]["pairwiseCriterionAgreement"] is None


def test_same_id_with_replaced_definition_is_not_aggregated_as_one_criterion():
    first, second = cases()[0], copy.deepcopy(cases()[0])
    second["id"] = "changed"
    second["request"]["criteria"][0]["description"] = "A different active requirement"
    second["inputFingerprint"] = fingerprint(
        {k: v for k, v in second.items() if k not in {"id", "inputFingerprint"}}
    )
    a, b = prediction(), prediction()
    b.update(caseId="changed", inputFingerprint=second["inputFingerprint"])
    report = compare_runs(
        [a, b],
        [a, b],
        [first, second],
        {
            "case": prediction()["answers"],
            "changed": prediction()["answers"],
        },
    )
    rows = [r for r in report["after"]["byCriterion"].values() if r["criterionId"] == "g"]
    assert len(rows) == 2
    assert all(r["total"] == 1 for r in rows)


def test_repo_paths_and_embedded_labels_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        private_path(__file__)
    payload = {"cases": [{"id": "c", "request": request().model_dump(), "expected": []}]}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="never expected labels"):
        load_cases(path)


def test_empty_sandbox_marker_is_not_a_repository_but_git_metadata_is(tmp_path):
    marker = tmp_path / ".git"
    marker.mkdir()
    destination = tmp_path / "private" / "report.json"
    assert private_path(destination) == destination
    (marker / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        private_path(destination)


def test_linked_worktree_marker_still_protects_private_benchmark_paths(tmp_path):
    (tmp_path / ".git").write_text("gitdir: /private/git/worktrees/test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        private_path(tmp_path / "cases.json")


async def test_live_driver_never_exceeds_generation_budget(tmp_path, monkeypatch):
    from cqa.infra.llm.base import GeneratedJSON
    from cqa.infra.llm.ollama import OllamaProvider

    req = request().model_dump()
    req["criteria"] = req["criteria"][2:3]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [{"id": "c", "request": req}]}), encoding="utf-8")
    calls = []

    async def generate(self, messages, schema):
        calls.append(messages)
        finding = analysis().model_dump()["results"][2]
        return GeneratedJSON(
            {
                "summary": "Synthetic budget control test",
                "results": [finding],
                "applicability": [
                    {
                        "criterionId": "i",
                        "status": "not_applicable",
                        "reason": "The active N/A condition is satisfied in this synthetic record.",
                        "messageIds": ["m1"],
                    }
                ],
            },
            {"usage": {}},
        )

    monkeypatch.setattr(OllamaProvider, "generate", generate)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:11434",
        model="synthetic-local",
        cases=path,
        only=None,
        max_cases=2,
        repeats=2,
        max_evaluations=3,
        max_model_calls=1,
        deadline_seconds=30,
        output_dir=tmp_path / "out",
        context_size=32768,
        output_limit=5000,
        timeout=5,
    )
    assert await run(args) == 1
    assert len(calls) == 1
    output = json.loads((args.output_dir / "predictions.json").read_text(encoding="utf-8"))
    assert output["modelCalls"] == 1
    assert output["records"][0]["status"] == "failed"
    assert output["records"][0]["errorCode"] == "model_call_budget"
