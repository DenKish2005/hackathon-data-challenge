"""AI integration boundary. No competing scoring formula lives here."""

import json
from typing import Protocol

from pydantic import Field, StrictFloat, StrictStr

from cqa.backend.schemas import ChecklistView, ConversationDetail, Schema
from cqa.service import RULES, score


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
    def score(self, checklist: ChecklistView, result: EvaluationResult) -> dict: ...


class ExistingScoringAdapter:
    """Delegate to the team's existing deterministic engine in cqa.service."""

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
        return {"evaluator": self.name, **self.provider.configuration()}

    async def evaluate_conversation(self, conversation, checklist):
        schema = EvaluationResult.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": RULES + "\nReturn the following JSON schema (snake_case fields). "
                "For absent actions use checked_message_ids; N/A also requires na_reason. "
                "Do not invent message references.\n" + json.dumps(schema, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "conversation": conversation.model_dump(mode="json"),
                        "checklist": checklist.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        return EvaluationResult.model_validate(await self.provider.generate(messages, schema))


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
            "scorer": type(self.scorer).__qualname__,
        }

    async def run(self, conversation, checklist):
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
        return {
            **result.model_dump(mode="json"),
            **self.scorer.score(checklist, result),
            "stages": stages,
        }
