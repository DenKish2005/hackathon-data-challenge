"""Mocked model contracts, not a measurement of LLM assessment accuracy."""

import asyncio
import json

import httpx
import pytest

from cqa import criterion_agents as agents
from cqa.service import EvaluationRequest, Evaluator, Store


@pytest.fixture
def sample():
    return EvaluationRequest.model_validate(
        {
            "conversation_id": "new-phone-42",
            "language": "RU",
            "version": 7,
            "messages": [
                {"id": "start", "role": "client", "text": "Когда придёт перевод?", "time": "00:00"},
                {"id": "bot", "role": "bot", "text": "Ожидайте оператора.", "time": "00:01"},
                {
                    "id": "answer",
                    "role": "operator",
                    "text": "Здравствуйте, я Анна. Уточню статус перевода.",
                    "time": "00:08",
                },
            ],
            "criteria": [
                {
                    "id": "new-contact-v7",
                    "title": "Новое приветствие",
                    "description": "Представился оператор, а не бот",
                    "weight": 10,
                    "type": "binary",
                },
                {
                    "id": "arbitrary-scale",
                    "title": "Новая шкала",
                    "description": "Используй только актуальные ступени",
                    "weight": 20,
                    "type": "scale",
                    "scale": [0, 5, 10],
                },
                {
                    "id": "id-check-revised",
                    "title": "Проверка личности",
                    "description": "Нужно для защищённого действия",
                    "weight": 20,
                    "type": "binary",
                    "naAllowed": True,
                    "naCondition": "Общий вопрос без защищённого действия",
                },
                {
                    "id": "critical-custom",
                    "title": "Грубая ошибка",
                    "description": "Применяй текущее описание",
                    "weight": 0,
                    "type": "flag",
                },
            ],
        }
    )


def model_payload(request):
    payload = json.loads(request.content)
    content = json.loads(payload["messages"][1]["content"])
    return payload, content.get("input", content)


def response_for(content):
    return {
        "summary": "Проверены критерии по исходной реплике оператора",
        "results": [
            {
                "criterionId": criterion["id"],
                "answer": (
                    "Нет"
                    if criterion["type"] == "flag"
                    else "N/A"
                    if criterion.get("naAllowed")
                    else max(criterion["scale"])
                    if criterion["type"] == "scale"
                    else "Да"
                ),
                "reason": "Проверяемый ответ по полному исходному транскрипту",
                "evidenceId": "answer",
                "quote": "Здравствуйте, я Анна.",
                "checkedMessageIds": [message["id"] for message in content["messages"]],
                "confidence": 0.8,
            }
            for criterion in content["criteria"]
        ],
    }


def model_response(analysis):
    return httpx.Response(
        200,
        json={
            "message": {"content": json.dumps(analysis, ensure_ascii=False)},
            "eval_count": 3,
            "prompt_eval_count": 5,
        },
    )


async def test_dynamic_specialists_full_source_and_final_critic_score(
    tmp_path, monkeypatch, sample
):
    monkeypatch.setenv("CQA_STRATEGY", "multi_agent")
    calls = []

    def respond(request):
        payload, content = model_payload(request)
        calls.append(payload)
        analysis = response_for(content)
        if "Final Critic" in payload["messages"][0]["content"]:
            analysis["results"][1]["answer"] = 5
            analysis["results"][-1]["answer"] = "Да"
            analysis["summary"] = "Финальный критик исправил промежуточный результат"
        return model_response(analysis)

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    result = await asyncio.wait_for(evaluator.evaluate(sample), timeout=2)
    assert len(calls) == len(sample.criteria) + 1
    assert result["passes"] == 5
    assert result["tokens"] == 40
    assert result["score"] == 66.67  # N/A excluded; critic's 5/10 scale used.
    assert result["critical"] is True  # Flag does not zero the weighted score.
    assert result["summary"].startswith("Финальный критик")
    assert result["strategy"] == "multi_agent"
    assert result["agentPromptVersion"] == agents.PROMPT_VERSION
    assert [run["criterionIds"] for run in result["agentRuns"][:-1]] == [
        [criterion.id] for criterion in sample.criteria
    ]
    for payload, criterion in zip(calls[:-1], sample.criteria, strict=True):
        supplied = json.loads(payload["messages"][1]["content"])
        assert supplied["messages"] == [message.model_dump() for message in sample.messages]
        assert supplied["criteria"] == [criterion.model_dump()]
        assert "Criterion Specialist" in payload["messages"][0]["content"]
    critic = json.loads(calls[-1]["messages"][1]["content"])
    assert critic["input"] == sample.model_dump(exclude={"force"})
    assert {item["criterionId"] for item in critic["specialistFindings"]} == {
        criterion.id for criterion in sample.criteria
    }
    assert len(evaluator.store.history(sample.conversation_id)) == 1


async def test_cache_tracks_rules_prompt_and_strategy_not_concurrency(
    tmp_path, monkeypatch, sample
):
    calls = []

    def respond(request):
        payload, content = model_payload(request)
        calls.append(payload)
        return model_response(response_for(content))

    store = Store(str(tmp_path / "db"))
    transport = httpx.MockTransport(respond)
    legacy = Evaluator(store, transport)
    await legacy.evaluate(sample)
    assert len(calls) == 2
    monkeypatch.setenv("CQA_STRATEGY", "multi_agent")
    multi = Evaluator(store, transport)
    await multi.evaluate(sample)
    assert len(calls) == 7
    assert (await multi.evaluate(sample))["cached"] is True
    assert len(calls) == 7
    monkeypatch.setenv("CQA_AGENT_CONCURRENCY", "3")
    assert (await Evaluator(store, transport).evaluate(sample))["cached"] is True
    assert len(calls) == 7
    changed = sample.model_copy(deep=True)
    changed.criteria[0].id = "replacement-rule"
    changed.criteria[0].description = "Изменённое правило организаторов"
    await multi.evaluate(changed)
    assert len(calls) == 12
    assert json.loads(calls[-1]["messages"][1]["content"])["input"]["criteria"][0]["id"] == (
        "replacement-rule"
    )
    monkeypatch.setattr(agents, "SPECIALIST_PROMPT", agents.SPECIALIST_PROMPT + "\nНовая версия.")
    await multi.evaluate(sample)
    assert len(calls) == 17


async def test_worker_failure_cancels_siblings_without_saving_partial(
    tmp_path, monkeypatch, sample
):
    monkeypatch.setenv("CQA_STRATEGY", "multi_agent")
    monkeypatch.setenv("CQA_CONCURRENCY", "2")
    monkeypatch.setenv("CQA_AGENT_CONCURRENCY", "2")
    critic_calls = []
    cancelled = asyncio.Event()

    async def respond(request):
        payload, content = model_payload(request)
        if "Final Critic" in payload["messages"][0]["content"]:
            critic_calls.append(payload)
        if content["criteria"][0]["id"] == "new-contact-v7":
            await asyncio.sleep(0.001)
            raise httpx.ConnectError("model offline", request=request)
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return model_response(response_for(content))

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    with pytest.raises(httpx.ConnectError):
        await evaluator.evaluate(sample)
    assert cancelled.is_set()
    assert critic_calls == []
    assert evaluator.store.history(sample.conversation_id) == []


@pytest.mark.parametrize("phase", ["specialist", "critic"])
async def test_invented_evidence_exhausts_repairs_and_never_persists(
    tmp_path, monkeypatch, sample, phase
):
    monkeypatch.setenv("CQA_STRATEGY", "multi_agent")
    rejected = 0

    def respond(request):
        nonlocal rejected
        payload, content = model_payload(request)
        analysis = response_for(content)
        critic = "Final Critic" in payload["messages"][0]["content"]
        if critic == (phase == "critic"):
            analysis["results"][0]["quote"] = "Этой цитаты нет в исходном тексте"
            rejected += 1
        return model_response(analysis)

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    with pytest.raises(ValueError, match="после исправлений"):
        await evaluator.evaluate(sample)
    assert rejected >= 3
    if phase == "critic":
        assert rejected == 3
    assert evaluator.store.history(sample.conversation_id) == []


async def test_model_concurrency_is_global_across_requests(tmp_path, monkeypatch, sample):
    monkeypatch.setenv("CQA_STRATEGY", "multi_agent")
    monkeypatch.setenv("CQA_CONCURRENCY", "2")
    monkeypatch.setenv("CQA_AGENT_CONCURRENCY", "3")
    active = peak = 0

    async def respond(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.002)
            _payload, content = model_payload(request)
            return model_response(response_for(content))
        finally:
            active -= 1

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(respond))
    other = sample.model_copy(update={"conversation_id": "second-dialogue"})
    results = await asyncio.wait_for(
        asyncio.gather(evaluator.evaluate(sample), evaluator.evaluate(other)), timeout=2
    )
    assert len(results) == 2
    assert peak == 2
    assert all(result["passes"] == 5 for result in results)
    assert len(evaluator.store.history(sample.conversation_id)) == 1
    assert len(evaluator.store.history(other.conversation_id)) == 1


@pytest.mark.parametrize(
    "setting,value", [("CQA_STRATEGY", "unknown"), ("CQA_AGENT_CONCURRENCY", "0")]
)
def test_invalid_agent_configuration_fails_explicitly(tmp_path, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError, match=setting):
        Evaluator(Store(str(tmp_path / "db")))
