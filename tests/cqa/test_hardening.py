"""Synthetic semantic/contract regressions; no private DEV content or network calls."""

import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from cqa import api
from cqa.backend.config import Settings
from cqa.infra.llm.ollama import OllamaProvider
from cqa.infra.llm.openai_compatible import OpenAICompatibleProvider
from cqa.infra.orchestrator.pipeline import Pipeline, ProviderCritic, ProviderEvaluator
from cqa.normalization import repair_mojibake
from cqa.prompts import build_messages, critic_instruction, profile
from cqa.service import (
    Analysis,
    ClientRequest,
    EvaluationRequest,
    Evaluator,
    Store,
    analysis_schema,
    parse_analysis,
    score,
    validate_analysis,
)
from cqa.workspace import default_checklist, normalize_records

from .test_evaluation import analysis, request


def original(index, *, text="Hello, I am Alex. Goodbye.", role="operator"):
    data = request().model_dump()
    data["criteria"] = [default_checklist()[index]]
    data["messages"] = [{"id": "m1", "role": role, "text": text, "time": "00:00"}]
    return EvaluationRequest.model_validate(data)


def finding(req, answer="Да", **updates):
    value = {
        "criterionId": req.criteria[0].id,
        "answer": answer,
        "reason": "Specific synthetic observation of the supplied message.",
        "evidenceId": "m1",
        "quote": req.messages[0].text,
        "checkedMessageIds": ["m1"],
    }
    value.update(updates)
    return Analysis.model_validate({"summary": "Synthetic test result", "results": [value]})


def test_reference_profiles_match_definitions_not_ids_or_weights():
    for i, name in enumerate(
        [
            "contact",
            "needs",
            "identity",
            "consultation",
            "empathy",
            "management",
            "closing",
            "severe",
        ]
    ):
        c = original(i).criteria[0]
        assert profile(c) == name
        c.id, c.weight = "unseen-id", 0
        assert profile(c) == name
        c.description = "An unrelated criterion"
        assert profile(c) is None


def test_prompt_exposes_role_boundary_without_inventing_semantic_facts():
    req = request()
    req.messages.insert(0, req.messages[0].model_copy(update={"id": "bot-before", "role": "bot"}))
    value = json.loads(build_messages(req)[1]["content"])["dialogueFacts"]
    assert value["preOperatorMessageIds"] == ["bot-before"]
    assert value["firstOperatorMessageId"] == "m1"
    assert value["humanOperatorMessageIds"] == ["m1"]


def test_replacement_has_no_old_instructions_in_draft_or_critic():
    req = original(6)
    assert "summary OR offer" in str(build_messages(req))
    req.criteria[0].description = "Provide clear next-action instructions."
    req.criteria[0].title = "Next action"
    req.criteria[0].naAllowed = False
    req.criteria[0].naCondition = ""
    draft = str(build_messages(req))
    critic = critic_instruction(req.criteria)
    for text in (draft, critic):
        assert "summary OR offer" not in text
        assert "interruptionPreventedClosing" not in text
        assert "goodbye/closing" not in text
    assert "Provide clear next-action" in draft


def test_custom_add_remove_scales_weights_and_schema():
    data = request().model_dump()
    data["criteria"] = [
        {
            "id": "next/action",
            "title": "Next action",
            "description": "Explain next action",
            "weight": 37.5,
            "type": "scale",
            "scale": [0, 2, 6],
        }
    ]
    req = EvaluationRequest.model_validate(data)
    a = finding(req, 2)
    validate_analysis(req, a)
    assert score(req.criteria, a.results)["score"] == 33.33
    schema = analysis_schema(req)
    item = schema["properties"]["results"]["items"]
    assert schema_answers(item) == {"0", "2", "6"}
    added = {**data["criteria"][0], "id": "new", "weight": 2}
    data["criteria"].append(added)
    req = EvaluationRequest.model_validate(data)
    assert analysis_schema(req)["properties"]["results"]["minItems"] == 2
    data["criteria"].pop(0)
    assert EvaluationRequest.model_validate(data).criteria[0].id == "new"


def test_schema_preserves_exact_cyrillic_answers_and_required_observations():
    req = original(0)
    schema = analysis_schema(req)
    item = schema["properties"]["results"]["items"]
    absent = item["anyOf"][-1]
    assert absent["properties"]["answer"]["enum"] == ["Нет"]
    assert absent["properties"]["evidenceBasis"] == {"const": "absence"}
    item = item["anyOf"][0]
    assert item["properties"]["answer"]["enum"] == ["Да"]
    assert item["properties"]["evidenceId"]["enum"] == ["m1"]
    assert item["properties"]["checks"]["required"] == ["firstGreeting", "firstIntroduction"]
    assert "checks" in item["required"]
    multi = analysis_schema(request())["properties"]["results"]
    assert [
        v["anyOf"][0]["properties"]["criterionId"]["enum"][0] for v in multi["prefixItems"]
    ] == [
        "g",
        "s",
        "i",
        "f",
    ]
    assert schema_answers(multi["prefixItems"][0]) == {"\u0414\u0430", "\u041d\u0435\u0442"}
    assert schema_answers(multi["prefixItems"][1]) == {"0", "5", "10", "15", "20"}


def schema_answers(item):
    return {
        value
        for branch in item.get("anyOf", [item])
        for value in branch["properties"]["answer"]["enum"]
    }


def test_model_score_strings_are_normalized_without_weakening_public_validation():
    req = request()
    value = analysis().model_dump()
    value["results"][1]["answer"] = "15"
    parsed = parse_analysis(json.dumps(value), req)
    validate_analysis(req, parsed)
    assert parsed.results[1].answer == 15.0
    assert parsed.results[1].confidence is None
    with pytest.raises(ValueError):
        validate_analysis(req, Analysis.model_validate(value))
    value["results"][1]["answer"] = "13"
    with pytest.raises(ValueError):
        validate_analysis(req, parse_analysis(json.dumps(value), req))


def test_bot_cannot_substantiate_positive_human_behavior():
    req = original(0, role="bot")
    with pytest.raises(ValueError, match="operator evidence"):
        validate_analysis(
            req, finding(req, checks={"firstGreeting": True, "firstIntroduction": True})
        )


@pytest.mark.parametrize("change", ["quote", "role", "id"])
def test_multimessage_grounding(change):
    req = request()
    a = analysis()
    record = {
        "messageId": "m1",
        "role": "operator",
        "quote": "Мен Алия",
        "relevance": "Operator introduces herself",
    }
    if change == "quote":
        record["quote"] = "Invented text"
    if change == "role":
        record["role"] = "bot"
    if change == "id":
        record["messageId"] = "missing"
    a.results[0].evidence = [api_evidence(record)]
    with pytest.raises(ValueError):
        validate_analysis(req, a)


def api_evidence(record):
    from cqa.service import Evidence

    return Evidence.model_validate(record)


def test_additional_grounded_messages_are_supported():
    req = request()
    req.messages.append(
        req.messages[0].model_copy(update={"id": "m2", "role": "client", "text": "Thanks"})
    )
    a = analysis()
    a.results[0].checkedMessageIds.append("m2")
    a.results[0].evidence = [
        api_evidence(
            {
                "messageId": "m2",
                "role": "client",
                "quote": "Thanks",
                "relevance": "Client acknowledges the answer",
            }
        )
    ]
    validate_analysis(req, a)


def test_request_inventory_links_sources_and_flags_unresolved_questions():
    req = original(3, text="Open settings.")
    req.messages.insert(
        0, req.messages[0].model_copy(update={"id": "c1", "role": "client", "text": "Where?"})
    )
    req.messages.append(req.messages[0].model_copy(update={"id": "c2", "text": "When?"}))
    value = finding(req, 20, quote="Open settings.")
    value.requests = [
        ClientRequest(
            messageId="c1",
            request="Where to act?",
            operatorMessageIds=["m1"],
            resolution="answered",
        ),
        ClientRequest(messageId="c2", request="When to retry?", resolution="unanswered"),
    ]
    validate_analysis(req, value)
    assert value.results[0].reviewRecommended
    assert "unresolved" in value.results[0].reviewReason
    value.requests[0].operatorMessageIds = ["c2"]
    with pytest.raises(ValueError, match="operator messages"):
        validate_analysis(req, value)


@pytest.mark.parametrize("invalid_review", [False, True])
async def test_sensitive_review_is_independent_and_does_not_zero_percentage(
    tmp_path, invalid_review
):
    req = original(2, text="Your account balance is 100.")
    req.criteria.extend([original(7).criteria[0], request().criteria[0]])
    draft_value = Analysis.model_validate(
        {
            "summary": "Synthetic privacy assessment",
            "results": [
                {
                    "criterionId": cid,
                    "answer": answer,
                    "reason": "Synthetic source-grounded observation.",
                    "evidenceId": "m1",
                    "quote": req.messages[0].text,
                    "checkedMessageIds": ["m1"],
                }
                for cid, answer in [("3", "Нет"), ("8", "Нет"), ("g", "Да")]
            ],
        }
    )
    severe = finding(
        req.model_copy(update={"criteria": [req.criteria[1]]}),
        "Да",
        evidenceBasis="direct",
        violationType="confidential_disclosure",
    )
    if invalid_review:
        severe.results[0].quote = "Fabricated confidential disclosure."
    count = 0

    def respond(request):
        nonlocal count
        count += 1
        value = draft_value if count <= 2 else severe
        return httpx.Response(200, json={"message": {"content": value.model_dump_json()}})

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    result = await evaluator.evaluate(req)
    assert result["critical"] is (not invalid_review) and result["score"] == 33.33
    if invalid_review:
        assert result["riskReview"]["status"] == "review_required"
        assert result["results"][1]["answer"] == draft_value.results[1].answer
        assert result["results"][1]["quote"] == req.messages[0].text
        assert result["results"][1]["reviewRecommended"]
        assert evaluator.store.history(req.conversation_id)[0]["critical"] is False
    else:
        assert result["riskReview"]["answerChanged"]
    assert not any(c["answerChanged"] for c in result["criticChanges"])
    assert result["usage"][-1]["phase"] == "risk_review"


def test_grounding_feedback_identifies_exact_source_and_missing_checked_reference():
    req = original(1)
    req.messages.append(
        req.messages[0].model_copy(update={"id": "m2", "text": "Which platform do you use?"})
    )
    value = finding(req, quote=req.messages[1].text, checkedMessageIds=["m1", "m2"])
    with pytest.raises(ValueError, match='exact source IDs for this quote: \\["m2"\\]'):
        validate_analysis(req, value)
    value.results[0].evidenceId = "m2"
    value.results[0].checkedMessageIds = ["m1"]
    with pytest.raises(ValueError, match="quote is exact in m2.*missing"):
        validate_analysis(req, value)
    value.results[0].checkedMessageIds.append("m2")
    validate_analysis(req, value)


def test_absence_preserves_legacy_fields_without_fabricated_quote():
    req = request().model_copy(update={"criteria": request().criteria[:1]})
    a = finding(req, "Нет", evidenceBasis="absence", evidenceId="", quote="")
    validate_analysis(req, a)
    assert a.results[0].model_dump()["quote"] == ""
    with pytest.raises(ValueError, match="absence"):
        validate_analysis(req, finding(req, "Да", evidenceBasis="absence", evidenceId="", quote=""))


@pytest.mark.parametrize("text", ["Goodbye.", "До свидания!", "Сау болыңыз!"])
def test_courtesy_only_severe_evidence_rejected(text):
    req = original(7, text=text)
    with pytest.raises(ValueError, match="courtesy-only"):
        validate_analysis(req, finding(req, checks={"qualifyingAct": True}, violationType="insult"))


def test_qualifying_severe_act_reviewed_but_does_not_zero_score():
    req = original(7, text="You are an idiot.")
    a = finding(req, checks={"qualifyingAct": True}, violationType="insult")
    validate_analysis(req, a)
    assert a.results[0].reviewRecommended
    assert score(req.criteria, a.results) == {"score": None, "critical": True}


def test_original_applicability_and_closing_contradictions_are_reviewed():
    cases = [
        (1, "N/A", {"sufficientAtJoin": False, "necessaryClarificationUsed": False}),
        (
            6,
            "\u0414\u0430",
            {"summaryOrHelp": False, "goodbye": True, "interruptionPreventedClosing": False},
        ),
        (2, "\u0414\u0430", {"verificationRequired": True, "verifiedBeforeAction": False}),
        (3, "N/A", {"clientRequestFormulated": True}),
    ]
    for index, answer, checks in cases:
        req = original(index)
        value = finding(req, answer, checks=checks)
        validate_analysis(req, value)
        assert value.results[0].reviewRecommended
        assert value.results[0].reviewReason.startswith("Self-check conflict:")
        assert value.results[0].answer == answer


def test_uncertainty_and_incomplete_context_are_review_metadata():
    req = request().model_copy(update={"context": {"incomplete": True}})
    a = analysis()
    a.results[0].uncertaintyNotes = ["No authorized knowledge source supplied"]
    validate_analysis(req, a)
    assert all(r.reviewRecommended for r in a.results)
    assert a.results[0].answer == "Да"


@pytest.mark.parametrize(
    "text", ["Здравствуйте, я Анна", "Сәлеметсіз бе, мен Алия", "Hello, I am Alex"]
)
def test_normalization_preserves_correct_multilingual_text(text):
    assert repair_mojibake(text) == text
    if not text.isascii():
        assert repair_mojibake(text.encode().decode("latin-1")) == text


def test_import_preserves_raw_record_ids_and_timestamps():
    raw = "Сәлеметсіз бе".encode().decode("latin-1")
    source = {
        "conversation_id": "synthetic-normalization",
        "language": "KZ",
        "channel": "agent chat",
        "transcript": [{"speaker": "operator", "text": raw, "timestamp": "00:03"}],
    }
    before = copy.deepcopy(source)
    dialog = normalize_records([source], default_checklist(), 1)[0]
    assert dialog["messages"][0] == {
        "id": "m1",
        "role": "operator",
        "text": "Сәлеметсіз бе",
        "time": "00:03",
    }
    assert dialog["originalRecord"] == before == source


def test_decimal_boundaries_all_na_and_independent_critical_flag():
    for value, expected in [(1.005, 1.01), (50.625, 50.63)]:
        c = SimpleNamespace(id="x", weight=1, type="scale", scale=[0, value, 100])
        assert score([c], [SimpleNamespace(criterionId="x", answer=value)])["score"] == expected
    c = SimpleNamespace(id="n", weight=1, type="binary", scale=[])
    assert score([c], [SimpleNamespace(criterionId="n", answer="N/A")])["score"] is None


async def test_targeted_repair_preserves_valid_findings_and_mandatory_critic(tmp_path):
    calls = []
    invalid = analysis().model_dump()
    invalid["results"][0]["quote"] = "invented"
    fixed = analysis().model_dump()

    def respond(req):
        payload = json.loads(req.content)
        calls.append(payload)
        content = (
            invalid
            if len(calls) == 1
            else {**fixed, "results": fixed["results"][:1]}
            if len(calls) == 2
            else fixed
        )
        return httpx.Response(
            200,
            json={
                "model": "test-actual",
                "message": {"content": json.dumps(content)},
                "eval_count": 10,
            },
        )

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    result = await evaluator.evaluate(request())
    assert result["passes"] == 3
    assert calls[1]["format"]["properties"]["results"]["maxItems"] == 1
    repair_input = json.loads(calls[1]["messages"][1]["content"])["evaluation"]
    assert [c["id"] for c in repair_input["criteria"]] == ["g"]
    assert not any(m["role"] == "assistant" for m in calls[1]["messages"])
    assert result["usage"][1]["targeted"]
    assert result["usage"][-1]["phase"] == "critic"
    assert result["model"] == "test-actual"
    assert not any(c["answerChanged"] for c in result["criticChanges"])


async def test_critic_changes_are_recorded(tmp_path):
    count = 0

    def respond(req):
        nonlocal count
        count += 1
        value = analysis()
        if count == 2:
            value.results[1].answer = 10.0
        return httpx.Response(200, json={"message": {"content": value.model_dump_json()}})

    result = await Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond)).evaluate(
        request()
    )
    assert [r["criterionId"] for r in result["criticChanges"] if r["answerChanged"]] == ["s"]
    assert result["draftResults"][1]["answer"] == 15


@pytest.mark.parametrize(
    "setting,value", [("seed", 99), ("context_size", 131072), ("output_limit", 6000)]
)
async def test_inference_settings_invalidate_cache(tmp_path, setting, value):
    evaluator = Evaluator(
        Store(str(tmp_path / "db")),
        httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"message": {"content": analysis().model_dump_json()}}
            )
        ),
    )
    first = await evaluator.evaluate(request())
    assert (await evaluator.evaluate(request()))["cached"]
    setattr(evaluator, setting, value)
    second = await evaluator.evaluate(request())
    assert not second["cached"] and first["inputHash"] != second["inputHash"]


def test_api_legacy_contract_and_browser_normalization(tmp_path):
    raw = "Сәлеметсіз бе! Мен Алия.".encode().decode("latin-1")
    req = request().model_dump()
    req["messages"][0]["text"] = raw

    def respond(req):
        payload = json.loads(json.loads(req.content)["messages"][1]["content"])["evaluation"]
        value = analysis().model_dump()
        for finding in value["results"]:
            finding["evidenceId"] = payload["messages"][0]["id"]
            finding["checkedMessageIds"] = [payload["messages"][0]["id"]]
        return httpx.Response(
            200,
            json={"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}},
        )

    provider = OllamaProvider(
        "http://127.0.0.1:11434", "synthetic-contract", transport=httpx.MockTransport(respond)
    )
    evaluator = ProviderEvaluator(provider)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'foundation.db'}", timeout=5)
    app = api.create_app(settings, Pipeline(evaluator, critic=ProviderCritic(evaluator)))
    with TestClient(app) as client:
        response = client.post("/api/evaluate", json=req)
        assert response.status_code == 200
        value = response.json()
        assert value["messages"][0]["text"] == "Сәлеметсіз бе! Мен Алия."
        assert value["messages"][0]["id"] == "m1"
        assert value["normalization"]["changes"][0]["originalText"] == raw
        for key in ["evaluationId", "results", "score", "critical", "criteriaSnapshot", "passes"]:
            assert key in value
        assert (
            client.get("/api/history/unseen-1").json()[0]["evaluationId"] == value["evaluationId"]
        )


@pytest.mark.parametrize("provider_class", [OllamaProvider, OpenAICompatibleProvider])
def test_foundation_adapter_preserves_repairs_absence_and_additional_evidence(
    tmp_path, provider_class
):
    payload = request().model_dump()
    payload["messages"].append(
        {"id": "client-thanks", "role": "client", "text": "Thanks", "time": "00:03"}
    )
    calls = []

    def respond(req):
        body = json.loads(req.content)
        calls.append(body)
        data = json.loads(body["messages"][1]["content"])["evaluation"]
        refs = {"m1": data["messages"][0]["id"], "client": data["messages"][1]["id"]}
        value = analysis().model_dump()
        requested = {c["id"] for c in data["criteria"]}
        value["results"] = [r for r in value["results"] if r["criterionId"] in requested]
        for finding in value["results"]:
            finding.update(evidenceId=refs["m1"], checkedMessageIds=list(refs.values()))
            if finding["criterionId"] == "g":
                finding["quote"] = "Invented quote" if len(calls) == 1 else "Мен Алия"
                finding["evidence"] = [
                    {
                        "messageId": refs["client"],
                        "role": "client",
                        "quote": "Thanks",
                        "relevance": "Client acknowledgment",
                    }
                ]
            if finding["criterionId"] == "s":
                finding["answer"] = "10" if len(calls) == 3 else "15"
                finding["uncertaintyNotes"] = ["No authoritative knowledge supplied"]
            if finding["criterionId"] == "f":
                finding.update(evidenceBasis="absence", evidenceId="", quote="")
        if provider_class is OpenAICompatibleProvider:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(value)}}
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}},
        )

    provider = provider_class(
        "http://localhost:11434", "synthetic-contract", transport=httpx.MockTransport(respond)
    )
    evaluator = ProviderEvaluator(provider)
    app = api.create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'evidence.db'}", timeout=5),
        Pipeline(evaluator, critic=ProviderCritic(evaluator)),
    )
    with TestClient(app) as client:
        response = client.post("/api/evaluate", json=payload)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["passes"] == 3
        assert value["results"][0]["evidence"][0]["messageId"] == "client-thanks"
        assert value["results"][1]["answer"] == 10
        assert value["results"][-1]["evidenceBasis"] == "absence"
        assert value["results"][-1]["evidenceId"] == value["results"][-1]["quote"] == ""
        assert value["reviewRecommended"] and value["scoreProvisional"]
        changes = value["metadata"]["criticChanges"]
        assert [c["criterionId"] for c in changes if c["answerChanged"]] == ["s"]
        repaired = json.loads(calls[1]["messages"][1]["content"])["evaluation"]
        assert [c["id"] for c in repaired["criteria"]] == ["g"]
        if provider_class is OllamaProvider:
            assert calls[1]["format"]["properties"]["results"]["maxItems"] == 1
        else:
            prompt = calls[1]["messages"][0]["content"]
            schema = json.loads(prompt.split("Return JSON using this schema:\n")[1])
            assert schema["properties"]["results"]["maxItems"] == 1
            assert calls[1]["response_format"] == {"type": "json_object"}
        assert client.post("/api/evaluate", json=payload).json()["cached"]
        assert len(calls) == 3


def test_foundation_criterion_replacement_uses_active_prompt_and_wire_scale(tmp_path):
    req = original(6)
    req.criteria[0].title = "Next action"
    req.criteria[0].description = "Explain a clear next action: 4=complete, 2=partial, 0=missing."
    req.criteria[0].type = "scale"
    req.criteria[0].scale = [0.0, 2.0, 4.0]
    req.criteria[0].naAllowed = False
    req.criteria[0].naCondition = ""

    def respond(incoming):
        body = json.loads(incoming.content)
        content = json.loads(body["messages"][1]["content"])
        assert content["criterionGuidance"] == []
        assert content["evaluation"]["criteria"][0]["allowedAnswers"] == ["0", "2", "4"]
        assert "summary OR offer" not in str(body["messages"])
        assert "interruptionPreventedClosing" not in str(body["messages"])
        value = finding(req, "4").model_dump()
        mid = content["evaluation"]["messages"][0]["id"]
        value["results"][0].update(evidenceId=mid, checkedMessageIds=[mid])
        return httpx.Response(
            200,
            json={"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}},
        )

    provider = OllamaProvider(
        "http://localhost:11434", "synthetic-contract", transport=httpx.MockTransport(respond)
    )
    evaluator = ProviderEvaluator(provider)
    app = api.create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'replacement.db'}", timeout=5),
        Pipeline(evaluator, critic=ProviderCritic(evaluator)),
    )
    with TestClient(app) as client:
        response = client.post("/api/evaluate", json=req.model_dump())
        assert response.status_code == 200, response.text
        assert response.json()["results"][0]["answer"] == 4
        assert response.json()["passes"] == 2


async def test_unrepaired_evidence_never_persists(tmp_path):
    invalid = analysis()
    invalid.results[0].quote = "fabricated"
    evaluator = Evaluator(
        Store(str(tmp_path / "db")),
        httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"message": {"content": invalid.model_dump_json()}}
            )
        ),
    )
    with pytest.raises(ValueError, match="после исправлений"):
        await evaluator.evaluate(request())
    assert evaluator.store.history("unseen-1") == []


@pytest.mark.parametrize("change", ["weight", "scale", "na", "add", "remove", "id"])
async def test_all_checklist_edits_invalidate_existing_cache(tmp_path, change):
    def respond(req):
        payload = json.loads(json.loads(req.content)["messages"][1]["content"])["evaluation"]
        values = []
        for c in payload["criteria"]:
            value = analysis().model_dump()["results"][0]
            value.update(
                criterionId=c["id"], answer=c["scale"][0] if c["type"] == "scale" else "Нет"
            )
            values.append(value)
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"results": values, "summary": "Synthetic current-rubric result"}
                    )
                }
            },
        )

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    before = await evaluator.evaluate(request())
    data = request().model_dump()
    if change == "weight":
        data["criteria"][0]["weight"] = 11
    elif change == "scale":
        data["criteria"][1]["scale"] = [0, 2, 6]
    elif change == "na":
        data["criteria"][2].update(naAllowed=False, naCondition="")
    elif change == "add":
        data["criteria"].append({**data["criteria"][0], "id": "new-id"})
    elif change == "remove":
        data["criteria"].pop()
    else:
        data["criteria"][0]["id"] = "replacement-id"
    after = await evaluator.evaluate(EvaluationRequest.model_validate(data))
    assert not after["cached"]
    assert before["inputHash"] != after["inputHash"]
    assert before["checklistFingerprint"] != after["checklistFingerprint"]


async def test_malformed_output_is_repaired_before_critic(tmp_path):
    calls = []

    def respond(req):
        calls.append(req)
        value = "not JSON" if len(calls) == 1 else analysis().model_dump_json()
        return httpx.Response(200, json={"message": {"content": value}})

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    value = await evaluator.evaluate(request())
    assert value["passes"] == 3
    assert value["usage"][-1]["phase"] == "critic"


async def test_wall_clock_timeout_never_persists_a_fake_success(tmp_path):
    async def respond(req):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"message": {"content": analysis().model_dump_json()}})

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    evaluator.timeout = 0.01
    with pytest.raises(httpx.ReadTimeout, match="deadline"):
        await evaluator.evaluate(request())
    assert evaluator.store.history("unseen-1") == []


def test_absence_and_role_rules_do_not_change_numeric_scale_or_critical_math():
    req = original(7, text="You are an idiot.")
    a = finding(req, checks={"qualifyingAct": True}, violationType="insult")
    c = request().criteria[0]
    req.criteria.append(c)
    second = a.results[0].model_copy(
        update={"criterionId": c.id, "answer": "Да", "checks": {}, "violationType": None}
    )
    a.results.append(second)
    validate_analysis(req, a)
    assert score(req.criteria, a.results) == {"score": 100.0, "critical": True}
