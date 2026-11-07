"""AI integration boundary. No competing scoring formula lives here."""

import hashlib
import inspect
import json
from time import perf_counter
from typing import Protocol

from pydantic import Field, StrictFloat, StrictStr

from cqa.backend.schemas import ChecklistView, ConversationDetail, Schema
from cqa.service import CRITIC_RULES, RULES, Analysis, EvaluationRequest, score, validate_analysis


class Finding(Schema):
    criterion_id: str
    answer: StrictStr | StrictFloat
    explanation: str = Field(min_length=1, max_length=3000)
    message_ids: list[str] = Field(default_factory=list, max_length=500)
    checked_message_ids: list[str] = Field(default_factory=list, max_length=500)
    na_reason: str | None = Field(default=None, max_length=3000)


class EvaluationResult(Schema):
    findings: list[Finding] = Field(min_length=1, max_length=50)
    is_mock: bool = False
    metadata: dict = Field(default_factory=dict)


class Evaluator(Protocol):
    name: str
    model: str
    is_mock: bool

    def configuration(self) -> dict: ...

    async def evaluate_conversation(
        self,
        conversation: ConversationDetail,
        checklist: ChecklistView,
    ) -> EvaluationResult: ...


class Scorer(Protocol):
    def configuration(self) -> dict: ...

    def score(self, checklist: ChecklistView, result: EvaluationResult) -> dict: ...


class Critic(Protocol):
    def configuration(self) -> dict: ...

    async def review(
        self, conversation: ConversationDetail, checklist: ChecklistView, result: EvaluationResult
    ) -> EvaluationResult: ...


class ExistingScoringAdapter:
    """Delegate to the team's existing deterministic engine in cqa.service."""

    def configuration(self):
        return {
            "name": "cqa.service.score",
            "implementation": hashlib.sha256(inspect.getsource(score).encode()).hexdigest(),
        }

    def score(self, checklist, result):
        from types import SimpleNamespace

        return score(
            checklist.criteria,
            [SimpleNamespace(criterionId=f.criterion_id, answer=f.answer) for f in result.findings],
        )


def validate_result(result, conversation, checklist):
    result = EvaluationResult.model_validate(result)
    criteria = {c.id: c for c in checklist.criteria}
    ids = {m.message_id for m in conversation.messages}
    if len(result.findings) != len(criteria) or {f.criterion_id for f in result.findings} != set(
        criteria
    ):
        raise ValueError("Exactly one finding per criterion is required")
    for finding in result.findings:
        criterion = criteria[finding.criterion_id]
        allowed = criterion.scale if criterion.type == "scale" else ["Да", "Нет"]
        if criterion.naAllowed:
            allowed = [*allowed, "N/A"]
        if isinstance(finding.answer, bool) or finding.answer not in allowed:
            raise ValueError("Answer is outside the configured scale/applicability")
        for refs in (finding.message_ids, finding.checked_message_ids):
            if len(set(refs)) != len(refs) or not set(refs) <= ids:
                raise ValueError("Unknown or duplicated message reference")
        if not finding.message_ids and not finding.checked_message_ids:
            raise ValueError("Evidence or a checked range is required")
        if finding.answer in ("Нет", "N/A", 0) and not finding.checked_message_ids:
            raise ValueError("Missing actions require a checked range")
        if finding.answer == "N/A" and not (finding.na_reason or "").strip():
            raise ValueError("N/A requires an applicability explanation")
    return result


class MockEvaluator:
    name = "MockEvaluator"
    model = "synthetic-mock-v1"
    is_mock = True

    def configuration(self):
        return {"evaluator": self.name, "model": self.model, "version": 1}

    async def evaluate_conversation(self, conversation, checklist):
        # These are deliberate synthetic answers, not assertions about transcript contents.
        return EvaluationResult(
            is_mock=True,
            metadata={"notice": "Synthetic infrastructure test"},
            findings=[
                Finding(
                    criterion_id=c.id,
                    answer=min(c.scale) if c.type == "scale" else "Нет",
                    explanation="Synthetic mock answer; no semantic assessment was performed.",
                    checked_message_ids=[m.message_id for m in conversation.messages],
                )
                for c in checklist.criteria
            ],
        )


class ProviderEvaluator:
    name = "ProviderEvaluator"

    def __init__(self, provider):
        self.provider = provider
        self.model = provider.model
        self.is_mock = provider.is_mock

    def configuration(self):
        return {
            "evaluator": self.name,
            "adapter_version": 2,
            "rules": RULES,
            "schema": Analysis.model_json_schema(),
            **self.provider.configuration(),
        }

    def request_messages(self, conversation, checklist):
        # Reuse the AI owner's established prompt, output schema and quote validation.
        request = EvaluationRequest(
            conversation_id=conversation.conversation_id,
            language=conversation.language,
            version=checklist.version,
            criteria=checklist.criteria,
            messages=[
                {
                    "id": m.message_id,
                    "role": m.speaker,
                    "text": m.text,
                    "time": m.timestamp_original,
                }
                for m in conversation.messages
            ],
        )
        schema = Analysis.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": RULES
                + "\nReturn JSON using this schema:\n"
                + json.dumps(schema, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        **request.model_dump(mode="json", exclude={"force"}),
                        "channel": conversation.channel,
                        "checklist_id": checklist.checklist_id,
                        "sections": checklist.sections,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        return request, messages

    async def analyze(self, conversation, checklist, previous=None):
        request, messages = self.request_messages(conversation, checklist)
        if previous is not None:
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": json.dumps(previous.metadata["analysis"], ensure_ascii=False),
                    },
                    {"role": "user", "content": CRITIC_RULES},
                ]
            )
        generated = await self.provider.generate(messages, Analysis.model_json_schema())
        analysis = validate_analysis(request, Analysis.model_validate(generated))
        calls = [
            *(previous.metadata.get("calls", []) if previous else []),
            getattr(generated, "metadata", {}),
        ]
        return EvaluationResult(
            is_mock=self.is_mock,
            findings=[
                Finding(
                    criterion_id=f.criterionId,
                    answer=f.answer,
                    explanation=f.reason,
                    message_ids=[f.evidenceId],
                    checked_message_ids=f.checkedMessageIds,
                    na_reason=f.reason if f.answer == "N/A" else None,
                )
                for f in analysis.results
            ],
            metadata={
                "summary": analysis.summary,
                "quotes": {f.criterionId: f.quote for f in analysis.results},
                "analysis": analysis.model_dump(mode="json"),
                "calls": calls,
            },
        )

    async def evaluate_conversation(self, conversation, checklist):
        return await self.analyze(conversation, checklist)


class ProviderCritic:
    """Reuse the existing team's Critic instruction and exact quote validation."""

    def __init__(self, evaluator):
        self.evaluator = evaluator

    def configuration(self):
        return {"critic": CRITIC_RULES, "adapter": self.evaluator.configuration()}

    async def review(self, conversation, checklist, result):
        return await self.evaluator.analyze(conversation, checklist, result)


class Pipeline:
    def __init__(
        self, evaluator, scorer=None, extractor=None, classifier=None, critic=None, categories=None
    ):
        self.evaluator = evaluator
        self.scorer = scorer or ExistingScoringAdapter()
        self.extractor = extractor
        self.classifier = classifier
        self.critic = critic
        self.categories = categories or {}
        if classifier and not extractor:
            raise ValueError("Classifier requires an extractor")

    def configuration(self):
        # Optional agents must expose a versioned config to participate in cache keys.
        return {
            "evaluator": self.evaluator.configuration(),
            "stages": {
                name: stage.configuration() if stage else None
                for name, stage in (
                    ("extractor", self.extractor),
                    ("classifier", self.classifier),
                    ("critic", self.critic),
                )
            },
            "categories": self.categories,
            "scorer": self.scorer.configuration(),
        }

    async def run(self, conversation, checklist):
        started = perf_counter()
        stages = {}
        if self.extractor:
            facts = await self.extractor.extract(conversation)
            stages["extraction"] = facts
            if self.classifier:
                stages["classification"] = await self.classifier.classify(facts, self.categories)
        result = await self.evaluator.evaluate_conversation(conversation, checklist)
        result = validate_result(result, conversation, checklist)
        if self.critic:
            result = validate_result(
                await self.critic.review(conversation, checklist, result), conversation, checklist
            )
        # The infrastructure is authoritative about whether mock mode was used.
        result.is_mock = self.evaluator.is_mock
        result.metadata["duration_seconds"] = round(perf_counter() - started, 6)
        return {
            **result.model_dump(mode="json"),
            **self.scorer.score(checklist, result),
            "stages": stages,
        }
