"""Compact model wire, monotonic repairs and definition-scoped semantic checks."""

import copy
import json

import httpx
import pytest

from cqa.prompts import build_messages
from cqa.semantics import semantic_issues
from cqa.service import (
    Analysis,
    analyze_phase,
    compact_analysis_schema,
    exact_source_spans,
    merge_analysis,
    parse_analysis,
    require_consistent_semantics,
    validate_analysis,
)

from .test_hardening import original
from .test_semantics import custom, explicit


def compact(value):
    data = value.model_dump(exclude_defaults=True)
    decisions = {d["criterionId"]: d["status"] for d in data.pop("applicability")}
    for result in data["results"]:
        result["applicability"] = decisions[result["criterionId"]]
    return data


@pytest.mark.parametrize(
    "answer,status", [("Да", "applicable"), ("N/A", "not_applicable"), ("Нет", "uncertain")]
)
def test_compact_wire_expands_explicit_decision_without_inventing_answer(answer, status):
    req = custom()
    value = explicit(req, answer, status)
    wire = compact(value)
    result = parse_analysis(json.dumps(wire), req)
    validate_analysis(req, result)
    require_consistent_semantics(req, result)
    assert result.results[0].answer == answer
    assert result.applicability[0].status == status
    assert result.applicability[0].reason == result.results[0].reason
    assert result.results[0].confidence is None
    assert result.results[0].quote == value.results[0].quote


def test_compact_schema_retains_scoped_applicability_and_short_fields():
    req = custom()
    schema = compact_analysis_schema(req)
    assert "applicability" not in schema["properties"]
    branches = schema["properties"]["results"]["items"]["anyOf"]
    for branch in branches:
        props = branch["properties"]
        statuses = props["applicability"]["enum"]
        assert ("N/A" in props["answer"]["enum"]) == ("not_applicable" in statuses)
        assert "confidence" not in props
        assert "reviewReason" not in props
        assert props["review"]["maxLength"] == 140
        assert list(props)[:2] == ["criterionId", "applicability"]
    assert schema["$defs"]["Finding_reason"]["maxLength"] == 240


def test_compact_wire_does_not_bypass_grounding_or_allow_mixed_decisions():
    req = custom()
    wire = compact(explicit(req))
    wire["results"][0]["quote"] = "Invented quote"
    with pytest.raises(ValueError, match="quote"):
        validate_analysis(req, parse_analysis(json.dumps(wire), req))
    wire["applicability"] = []
    with pytest.raises(ValueError, match="mix"):
        parse_analysis(json.dumps(wire), req)


def test_source_choices_are_exact_bounded_and_not_translated_or_space_repaired():
    req = custom()
    req.messages[0].text = (
        "Hello! My name is Dana. "
        "Open the Help link in the website footer; it is available without signing in. "
        "That is the public Help page you asked for. Can I help with anything else? Goodbye!"
    )
    choices = exact_source_spans(req.messages)
    assert choices and len(choices) <= 64
    assert all(0 < len(q) <= 160 and q in req.messages[0].text for q in choices)
    assert "Hello! My name is Dana." in choices
    assert not any("helpwith" in q for q in choices)
    schema = compact_analysis_schema(req)
    assert schema["$defs"]["ExactSourceQuote"]["enum"] == choices


def test_long_source_choice_generation_is_bounded_without_dropping_input():
    req = custom()
    req.messages[0].text = " ".join(f"UniqueSentence{i}." for i in range(100))
    original_text = req.messages[0].text
    assert exact_source_spans(req.messages) is None
    assert "ExactSourceQuote" not in compact_analysis_schema(req)["$defs"]
    assert req.messages[0].text == original_text


def test_compact_na_conflict_and_partial_consultation_still_cannot_persist():
    req = custom()
    wire = compact(explicit(req, "Нет", "not_applicable"))
    value = parse_analysis(json.dumps(wire), req)
    validate_analysis(req, value)
    with pytest.raises(ValueError):
        require_consistent_semantics(req, value)
    from cqa.service import ClientRequest

    req = original(3)
    req.messages.append(req.messages[0].model_copy(update={"id": "client", "role": "client"}))
    value = explicit(req, 20, checks={"clientRequestFormulated": True})
    value.requests = [
        ClientRequest(
            messageId="client", request="A partially answered question", resolution="partial"
        )
    ]
    assert "Maximum consultation" in semantic_issues(req, value)[req.criteria[0].id]


def test_compact_review_preserves_material_uncertainty_and_rejects_ambiguous_metadata():
    req = custom()
    wire = compact(explicit(req))
    wire["results"][0]["review"] = "External account facts cannot be independently verified."
    result = parse_analysis(json.dumps(wire), req).results[0]
    assert result.reviewRecommended
    assert result.reviewReason == result.uncertaintyNotes[0]
    wire["results"][0]["reviewRecommended"] = False
    with pytest.raises(ValueError, match="mix"):
        parse_analysis(json.dumps(wire), req)


async def test_failed_provider_call_retains_phase_without_raw_transcript():
    from cqa.infra.llm.base import ProviderError, call_metrics
    from cqa.infra.llm.ollama import OllamaProvider
    from cqa.infra.orchestrator.pipeline import ProviderEvaluator
    from cqa.judge_benchmark import pipeline_inputs

    req = custom()
    _, conversation, checklist = pipeline_inputs(
        {
            "request": req.model_dump(),
            "channel": "agent chat",
            "checklistId": "test",
            "sections": [],
        }
    )

    def fail(request):
        raise httpx.ConnectError("Unavailable", request=request)

    provider = OllamaProvider(
        "http://127.0.0.1:11434", "synthetic", transport=httpx.MockTransport(fail), attempts=1
    )
    trace = []
    token = call_metrics.set(trace)
    try:
        with pytest.raises(ProviderError):
            await ProviderEvaluator(provider).evaluate_conversation(conversation, checklist)
    finally:
        call_metrics.reset(token)
    assert trace[0]["phase"] == "evaluate"
    assert trace[0]["status"] == "failed"
    assert req.messages[0].text not in json.dumps(trace)


async def test_repairs_keep_fixed_findings_when_another_finding_still_fails():
    req = custom()
    other = req.criteria[0].model_copy(update={"id": "other"})
    req.criteria.append(other)
    first = explicit(req.model_copy(update={"criteria": req.criteria[:1]}))
    second = explicit(req.model_copy(update={"criteria": [other]}))
    good = Analysis(
        summary="Synthetic repair test",
        results=first.results + second.results,
        applicability=first.applicability + second.applicability,
    )
    count = 0
    trace = []

    async def generate(messages, *, schema):
        nonlocal count
        count += 1
        ids = [c["id"] for c in json.loads(messages[1]["content"])["evaluation"]["criteria"]]
        candidate = good.model_copy(deep=True)
        if count == 1:
            for r in candidate.results:
                r.quote = "invented"
        elif count == 2:
            candidate.results[1].quote = "still invented"
        else:
            assert ids == ["other"]
            candidate.results = candidate.results[1:]
            candidate.applicability = candidate.applicability[1:]
        diagnostics = {}
        trace.append(diagnostics)
        return {"message": {"content": candidate.model_dump_json()}, "_diagnostics": diagnostics}

    calls = []
    result = await analyze_phase(req, build_messages(req), calls, "evaluate", generate)
    assert count == 3
    assert [r.quote for r in result.results] == [r.quote for r in good.results]
    assert trace[1]["validation"]["invalidCriterionIds"] == ["other"]
    assert trace[-1]["validation"]["validated"]


def test_targeted_merge_cannot_rewrite_unselected_criteria():
    req = custom()
    base = explicit(req)
    replacement = copy.deepcopy(base)
    replacement.results[0].criterionId = "not-selected"
    with pytest.raises(ValueError, match="selected"):
        merge_analysis(req, base, replacement, req.criteria)


@pytest.mark.parametrize("reason", ["Ответ: Нет.", "Final answer: no.", "Итоговая оценка: 15."])
def test_explicit_explanation_answer_conflict(reason):
    req = custom()
    value = explicit(req)
    value.results[0].reason = reason
    assert semantic_issues(req, value)


def test_excluded_timing_is_scoped_to_unchanged_definition_and_explicit_claim():
    req = original(5)
    value = explicit(req, 10)
    value.results[0].reason = "Оператор должен дать первый ответ в течение 3 минут."
    assert "excluded" in semantic_issues(req, value)[req.criteria[0].id]
    value.results[0].reason = "Порог первого ответа 3 минуты исключён из оценки."
    assert semantic_issues(req, value) == {}
    req.criteria[0].description = "Assess first response within 3 minutes."
    value.results[0].reason = "Оператор должен дать первый ответ в течение 3 минут."
    assert semantic_issues(req, value) == {}
