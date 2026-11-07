"""Synthetic decision/repair regressions, independent of private labels and live models."""

import json

import httpx
import pytest

from cqa.prompts import build_messages, profile
from cqa.semantics import review_targets, semantic_issues
from cqa.service import (
    Analysis,
    ApplicabilityDecision,
    ClientRequest,
    Evaluator,
    Store,
    analysis_schema,
    require_consistent_semantics,
    review_analysis,
    translate_analysis_ids,
    validate_analysis,
)

from .test_hardening import finding, original


def decision(req, status="applicable"):
    return ApplicabilityDecision(
        criterionId=req.criteria[0].id,
        status=status,
        reason="The active applicability condition was checked against the supplied record.",
        messageIds=[m.id for m in req.messages],
    )


def explicit(req, answer="Да", status="applicable", **updates):
    value = finding(req, answer, **updates)
    value.applicability = [decision(req, status)]
    return value


def custom():
    req = original(2)
    req.criteria[0].title = "Screenshot instructions"
    req.criteria[
        0
    ].description = "Explain how to attach a screenshot when the client reports an error."
    req.criteria[0].naCondition = "The client did not report an error."
    return req


@pytest.mark.parametrize(
    "status,answer", [("not_applicable", "Нет"), ("applicable", "N/A"), ("uncertain", "N/A")]
)
def test_generic_applicability_conflicts_cannot_be_final(status, answer):
    req = custom()
    value = explicit(req, answer, status)
    validate_analysis(req, value)
    with pytest.raises(ValueError, match="N/A"):
        require_consistent_semantics(req, value)
    assert value.results[0].answer == answer  # Never turn a model observation into a forced answer.


def test_unknown_applicability_is_provisional_not_a_weight_exclusion():
    req = custom()
    value = explicit(req, "Нет", "uncertain")
    validate_analysis(req, value)
    require_consistent_semantics(req, value)
    assert value.results[0].reviewRecommended
    assert value.results[0].answer == "Нет"


@pytest.mark.parametrize("source_ids", [["missing"], ["m1", "m1"]])
def test_applicability_requires_real_unique_source_ids(source_ids):
    req = custom()
    value = explicit(req)
    value.applicability[0].messageIds = source_ids
    with pytest.raises(ValueError, match="applicability source"):
        validate_analysis(req, value)


def test_applicability_must_cover_the_complete_active_rubric():
    req = custom()
    value = explicit(req)
    value.applicability.append(value.applicability[0].model_copy())
    with pytest.raises(ValueError, match="one applicability"):
        validate_analysis(req, value)


def test_compact_id_mapping_is_bijective_and_preserves_quotes_roles_and_applicability():
    req = custom()
    value = explicit(req)
    value.results[0].evidence = []
    saved = value.model_dump()
    mapped = translate_analysis_ids(value, {"m1": "canonical-source-123"})
    assert mapped.results[0].evidenceId == "canonical-source-123"
    assert mapped.applicability[0].messageIds == ["canonical-source-123"]
    assert mapped.results[0].quote == value.results[0].quote
    assert translate_analysis_ids(mapped, {"canonical-source-123": "m1"}).model_dump() == saved
    with pytest.raises(KeyError):
        translate_analysis_ids(value, {"unknown": "m1"})


def test_new_schema_requires_applicability_and_respects_changed_definitions():
    req = custom()
    assert profile(req.criteria[0]) is None
    schema = analysis_schema(req)
    assert "applicability" in schema["required"]
    item = schema["properties"]["applicability"]["items"]
    assert item["properties"]["criterionId"] == {"const": req.criteria[0].id}
    assert "not_applicable" in item["properties"]["status"]["enum"]
    req.criteria[0].naAllowed = False
    item = analysis_schema(req)["properties"]["applicability"]["items"]
    assert "not_applicable" not in item["properties"]["status"]["enum"]
    text = str(build_messages(req))
    assert "verificationRequired" not in text
    assert "attach a screenshot" in text


def test_explicit_conclusion_in_reason_cannot_disagree_with_answer():
    req = custom()
    value = explicit(req, "Нет")
    value.results[0].reason = "Следовательно, ответ N/A, а не Нет."
    assert "Explanation explicitly selects N/A" in semantic_issues(req, value)[req.criteria[0].id]
    value.results[0].reason = "The operator quoted the text 'answer N/A' from a help page."
    assert semantic_issues(req, value) == {}
    value.results[0].reason = "Ответ не N/A: отсутствует необходимая инструкция."
    assert semantic_issues(req, value) == {}


@pytest.mark.parametrize(
    "index,answer,status,checks",
    [
        (1, "Нет", "applicable", {"sufficientAtJoin": True, "necessaryClarificationUsed": False}),
        (1, "Да", "applicable", {"sufficientAtJoin": False, "necessaryClarificationUsed": False}),
        (2, "Нет", "applicable", {"verificationRequired": False, "verifiedBeforeAction": False}),
        (2, "Да", "applicable", {"verificationRequired": True, "verifiedBeforeAction": False}),
        (3, "N/A", "not_applicable", {"clientRequestFormulated": True}),
    ],
)
def test_definition_scoped_observations_must_agree_with_applicability(
    index, answer, status, checks
):
    req = original(index)
    value = explicit(req, answer, status, checks=checks)
    validate_analysis(req, value)
    with pytest.raises(ValueError):
        require_consistent_semantics(req, value)


def test_uncited_resolution_and_unanswered_request_block_maximum_consultation():
    req = original(3)
    req.messages.append(req.messages[0].model_copy(update={"id": "c1", "role": "client"}))
    value = explicit(req, 20, checks={"clientRequestFormulated": True})
    value.requests = [
        ClientRequest(messageId="c1", request="A substantive question", resolution="answered")
    ]
    assert "actual operator response" in semantic_issues(req, value)[req.criteria[0].id]
    value.requests[0].resolution = "unanswered"
    assert "Maximum consultation" in semantic_issues(req, value)[req.criteria[0].id]


async def test_focused_critic_corrects_dispute_and_preserves_unselected_finding(tmp_path):
    req = custom()
    simple = req.criteria[0].model_copy(
        update={"id": "another-rule", "naAllowed": False, "naCondition": "", "weight": 10.0}
    )
    req.criteria.insert(0, simple)
    one = req.model_copy(update={"criteria": [simple]})
    draft = explicit(one)
    selected = req.model_copy(update={"criteria": [req.criteria[1]]})
    disputed = explicit(selected, "Нет", "not_applicable")
    draft.results.extend(disputed.results)
    draft.applicability.extend(disputed.applicability)
    validate_analysis(req, draft)
    preserved = draft.results[0].model_dump()
    calls = []

    async def generate(messages, *, schema):
        data = json.loads(messages[1]["content"])["evaluation"]
        assert not any(message["role"] == "assistant" for message in messages)
        assert "Prior decisions (claims, not facts)" in messages[-1]["content"]
        assert [c["id"] for c in data["criteria"]] == [selected.criteria[0].id]
        assert schema["properties"]["results"]["maxItems"] == 1
        corrected = explicit(selected, "N/A", "not_applicable")
        return {"message": {"content": corrected.model_dump_json()}}

    final = await review_analysis(req, draft, calls, generate)
    assert final.results[0].model_dump() == preserved
    assert final.results[1].answer == "N/A"
    assert [d.status for d in final.applicability] == ["applicable", "not_applicable"]
    assert len(calls) == 1
    assert calls[0]["criterionIds"] == [selected.criteria[0].id]


async def test_critic_does_not_repeat_verbose_draft_in_prompt():
    req = custom()
    value = explicit(req, "N/A", "not_applicable")
    value.results[0].reviewRecommended = True
    value.results[0].reviewReason = "Verbose diagnostic sentence. " * 40
    value.results[0].uncertaintyNotes = ["Historical draft note not an authoritative fact"]

    async def generate(messages, *, schema):
        prompt = json.dumps(messages, ensure_ascii=False)
        assert "Verbose diagnostic sentence" not in prompt
        assert "Historical draft note" not in prompt
        assert req.messages[0].text in prompt
        assert "Draft requests review" in prompt
        return {"message": {"content": explicit(req, "N/A", "not_applicable").model_dump_json()}}

    await review_analysis(req, value, [], generate)


async def test_clean_simple_custom_finding_does_not_need_rewriting():
    req = custom()
    req.criteria[0].naAllowed = False
    value = explicit(req)
    validate_analysis(req, value)
    assert review_targets(req, value) == {}

    async def forbidden(*args, **kwargs):
        pytest.fail("No model call should rewrite an undisputed simple finding")

    assert await review_analysis(req, value, [], forbidden) is value


async def test_focused_critic_and_its_repairs_keep_foundation_channel_and_sections():
    req = custom()
    value = explicit(req, "N/A", "not_applicable")
    template = build_messages(req)
    payload = json.loads(template[1]["content"])
    extra = {"channel": "voice call", "checklist_id": "dynamic-call", "sections": ["Call rules"]}
    payload["evaluation"].update(extra)
    template[1]["content"] = json.dumps(payload)
    count = 0

    async def generate(messages, *, schema):
        nonlocal count
        count += 1
        actual = json.loads(messages[1]["content"])["evaluation"]
        assert all(actual[key] == expected for key, expected in extra.items())
        candidate = value.model_copy(deep=True)
        if count == 1:
            candidate.results[0].quote = "invented source span"
        return {"message": {"content": candidate.model_dump_json()}}

    final = await review_analysis(req, value, [], generate, prompt_messages=template)
    assert final.results[0].answer == "N/A"
    assert count == 2


async def test_unresolved_semantic_conflict_never_persists(tmp_path):
    req = custom()
    invalid = explicit(req, "Нет", "not_applicable")

    def respond(request):
        return httpx.Response(200, json={"message": {"content": invalid.model_dump_json()}})

    evaluator = Evaluator(Store(str(tmp_path / "test.sqlite3")), httpx.MockTransport(respond))
    with pytest.raises(ValueError, match="после исправлений"):
        await evaluator.evaluate(req)
    assert evaluator.store.history(req.conversation_id) == []


def test_legacy_analysis_remains_readable_but_is_not_claimed_semantically_complete():
    req = custom()
    value = Analysis.model_validate(finding(req).model_dump(exclude={"applicability"}))
    validate_analysis(req, value)
    assert value.results[0].reviewRecommended
    assert "Legacy output" in str(review_targets(req, value))


@pytest.mark.parametrize("critic_enabled", [False, True])
def test_foundation_never_persists_semantic_conflicts_even_without_critic(tmp_path, critic_enabled):
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from cqa.api import create_app
    from cqa.backend.config import Settings
    from cqa.backend.models import Evaluation
    from cqa.infra.llm.ollama import OllamaProvider
    from cqa.infra.orchestrator.pipeline import Pipeline, ProviderCritic, ProviderEvaluator

    req = custom()

    def respond(request):
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"])["evaluation"]["messages"][0]
        value = explicit(req, "Нет", "not_applicable").model_dump()
        value["applicability"][0]["messageIds"] = [source["id"]]
        value["results"][0].update(evidenceId=source["id"], checkedMessageIds=[source["id"]])
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(value)},
            },
        )

    provider = OllamaProvider(
        "http://127.0.0.1:11434", "synthetic", transport=httpx.MockTransport(respond)
    )
    evaluator = ProviderEvaluator(provider)
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'semantic.sqlite3'}", timeout=5),
        Pipeline(evaluator, critic=ProviderCritic(evaluator) if critic_enabled else None),
    )
    with TestClient(app) as client:
        response = client.post("/api/evaluate", json=req.model_dump())
        assert response.status_code == 502
        with app.state.db.sessions() as session:
            assert session.scalar(select(func.count()).select_from(Evaluation)) == 0
