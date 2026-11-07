"""Synthetic active-pipeline contracts, not a measurement of model accuracy."""

import asyncio
import copy
import json

import pytest

from cqa import criterion_agents
from cqa.backend.config import Settings
from cqa.backend.schemas import ChecklistView, ConversationDetail
from cqa.infra.orchestrator.pipeline import Pipeline, ProviderCritic, ProviderEvaluator


@pytest.fixture
def inputs():
    conversation = ConversationDetail(
        conversation_id="new-call",
        dataset_group_id="TEST",
        channel="voice call",
        language="RU",
        audio_url="https://example.test/audio.mp3",
        imported_at="2026-01-01",
        messages=[
            {
                "message_id": "client",
                "message_index": 0,
                "speaker": "client",
                "timestamp_original": "00:00",
                "text": "Когда придёт перевод?",
            },
            {
                "message_id": "operator",
                "message_index": 1,
                "speaker": "operator",
                "timestamp_original": "00:01",
                "text": "Здравствуйте, я Анна. Уточню статус перевода.",
            },
        ],
    )
    checklist = ChecklistView(
        checklist_id="dynamic",
        version=7,
        created_at="2026-01-01",
        sections=[],
        criteria=[
            {
                "id": "contact-custom",
                "title": "Приветствие",
                "description": "Представился оператор",
                "type": "binary",
                "weight": 10,
            },
            {
                "id": "scale-custom",
                "title": "Новая шкала",
                "description": "Новая шкала организаторов",
                "type": "scale",
                "scale": [0, 5, 10],
                "weight": 20,
            },
            {
                "id": "na-custom",
                "title": "Применимость",
                "description": "Защищённое действие",
                "type": "binary",
                "weight": 20,
                "naAllowed": True,
                "naCondition": "Общий вопрос",
            },
        ],
    )
    return conversation, checklist


class Provider:
    model = "synthetic-contract-provider"
    is_mock = False

    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.cancelled = asyncio.Event()

    def configuration(self):
        return {"model": self.model}

    async def generate(self, messages, schema):
        self.calls.append(copy.deepcopy(messages))
        data = json.loads(messages[1]["content"])["evaluation"]
        critic = len(messages) > 2
        if self.failure:
            await self.failure(self, data, critic)
        return {
            "summary": "Критик перепроверил выводы" if critic else "Специалист проверил критерий",
            "applicability": [
                {
                    "criterionId": c["id"],
                    "status": "not_applicable" if c.get("naAllowed") else "applicable",
                    "reason": "Применимость проверена по исходному диалогу",
                    "messageIds": [m["id"] for m in data["messages"]],
                }
                for c in data["criteria"]
            ],
            "results": [
                {
                    "criterionId": c["id"],
                    "answer": "N/A"
                    if c.get("naAllowed")
                    else ("5" if critic else "10")
                    if c["type"] == "scale"
                    else "Да",
                    "reason": "Вывод обоснован исходной репликой оператора",
                    "evidenceId": next(
                        m["id"] for m in data["messages"] if m["role"] == "operator"
                    ),
                    "quote": "Здравствуйте, я Анна.",
                    "checkedMessageIds": [m["id"] for m in data["messages"]],
                }
                for c in data["criteria"]
            ],
        }


def pipeline(provider, concurrency=1):
    evaluator = ProviderEvaluator(provider, strategy="multi_agent", agent_concurrency=concurrency)
    return Pipeline(evaluator, critic=ProviderCritic(evaluator))


async def test_active_specialists_keep_original_transcript_then_critic_scores(inputs):
    conversation, checklist = inputs
    provider = Provider()
    result = await pipeline(provider).run(conversation, checklist)
    assert len(provider.calls) == 4
    assert result["score"] == 66.67  # N/A excluded; final critic lowers 10/10 to 5/10.
    assert result["metadata"]["strategy"] == "multi_agent"
    assert [r["role"] for r in result["metadata"]["agentRuns"]] == [
        "criterion_specialist",
        "criterion_specialist",
        "criterion_specialist",
        "critic",
    ]
    for messages, criterion in zip(provider.calls[:-1], checklist.criteria, strict=True):
        data = json.loads(messages[1]["content"])["evaluation"]
        assert [c["id"] for c in data["criteria"]] == [criterion.id]
        assert [m["text"] for m in data["messages"]] == [m.text for m in conversation.messages]
        assert "Criterion Specialist" in messages[0]["content"]
    assert result["metadata"]["agentRuns"][-1]["criterionIds"] == ["scale-custom", "na-custom"]
    final = provider.calls[-1]
    assert len(json.loads(final[1]["content"])["evaluation"]["criteria"]) == 2
    assert final[2]["role"] == "user"
    assert "Reassess independently" in final[2]["content"]
    assert len(result["metadata"]["analysis"]["applicability"]) == len(checklist.criteria)
    assert result["metadata"]["semanticValidation"]["explicitApplicability"] is True
    assert {r["messageIds"][0] for r in result["metadata"]["analysis"]["applicability"]} == {
        "client"
    }
    assert result["metadata"]["criticChanges"][1]["answerChanged"] is True


async def test_worker_failure_cancels_siblings_and_never_calls_critic(inputs):
    async def fail(provider, data, critic):
        assert not critic
        if data["criteria"][0]["id"] == "contact-custom":
            await asyncio.sleep(0.01)
            raise ConnectionError("Synthetic provider unavailable")
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            provider.cancelled.set()
            raise

    provider = Provider(fail)
    with pytest.raises(ConnectionError):
        await pipeline(provider, concurrency=2).run(*inputs)
    assert provider.cancelled.is_set()
    assert all(len(messages) == 2 for messages in provider.calls)


async def test_specialist_hallucinated_quote_exhausts_shared_grounding_repairs(inputs):
    class Hallucinating(Provider):
        async def generate(self, messages, schema):
            result = await super().generate(messages, schema)
            result["results"][0]["quote"] = "This never appeared in the transcript"
            return result

    provider = Hallucinating()
    with pytest.raises(ValueError, match="проверяемую оценку"):
        await pipeline(provider).run(*inputs)
    assert 3 <= len(provider.calls) <= 3 * len(inputs[1].criteria)
    assert all(
        len(json.loads(messages[1]["content"])["evaluation"]["criteria"]) == 1
        for messages in provider.calls
    )
    assert all(
        "Criterion Specialist" in messages[0]["content"] or len(messages) > 2
        for messages in provider.calls
    )


def test_cache_configuration_tracks_strategy_and_actual_specialist_instructions(monkeypatch):
    provider = Provider()
    default = ProviderEvaluator(provider).configuration()
    multi = ProviderEvaluator(provider, strategy="multi_agent").configuration()
    assert multi != default
    assert (
        ProviderEvaluator(provider, strategy="multi_agent", agent_concurrency=3).configuration()
        == multi
    )
    monkeypatch.setattr(
        criterion_agents, "SPECIALIST_PROMPT", criterion_agents.SPECIALIST_PROMPT + " revised"
    )
    assert ProviderEvaluator(provider, strategy="multi_agent").configuration() != multi


@pytest.mark.parametrize(
    "settings",
    [
        {"strategy": "unknown"},
        {"agent_concurrency": 0},
        {"strategy": "multi_agent", "critic_enabled": False},
    ],
)
def test_invalid_strategy_fails_explicitly(settings):
    with pytest.raises(ValueError):
        Settings(**settings)
