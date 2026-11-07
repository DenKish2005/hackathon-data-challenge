"""AI integration boundary. No competing scoring formula lives here."""

import hashlib
import inspect
import json
from time import perf_counter
from typing import Protocol

from pydantic import Field, StrictFloat, StrictStr

from cqa.backend.schemas import ChecklistView, ConversationDetail, Schema
from cqa.infra.llm.openai_compatible import OpenAICompatibleProvider
from cqa.normalization import NORMALIZATION_VERSION
from cqa.prompts import (
    CRITIC_RULES,
    GUIDANCE,
    PIPELINE_VERSION,
    PROMPT_VERSION,
    REFERENCE,
    RULES,
    SCHEMA_VERSION,
    build_messages,
    fingerprint,
)
from cqa.semantics import review_targets
from cqa.service import (
    Analysis,
    EvaluationRequest,
    analyze_phase,
    require_consistent_semantics,
    review_analysis,
    score,
    translate_analysis_ids,
    validate_analysis,
)


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
            **self.provider.configuration(),
            "evaluator": self.name,
            "adapter_version": 5,
            "rules": RULES,
            "schema": Analysis.model_json_schema(),
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "reference_guidance": GUIDANCE,
            "reference_definitions": REFERENCE,
            "normalization_version": NORMALIZATION_VERSION,
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
        messages = build_messages(request)
        payload = json.loads(messages[1]["content"])
        payload["evaluation"].update(
            channel=conversation.channel,
            checklist_id=checklist.checklist_id,
            sections=checklist.sections,
        )
        messages[1]["content"] = json.dumps(payload, ensure_ascii=False)
        return request, messages

    async def analyze(self, conversation, checklist, previous=None):
        canonical, original_messages = self.request_messages(conversation, checklist)
        aliases = {m.id: f"m{i + 1}" for i, m in enumerate(canonical.messages)}
        sources = {alias: mid for mid, alias in aliases.items()}
        request = canonical.model_copy(
            update={
                "messages": [m.model_copy(update={"id": aliases[m.id]}) for m in canonical.messages]
            }
        )
        messages = build_messages(request)
        payload = json.loads(messages[1]["content"])
        original_payload = json.loads(original_messages[1]["content"])["evaluation"]
        payload["evaluation"].update(
            {key: original_payload[key] for key in ("channel", "checklist_id", "sections")}
        )
        messages[1]["content"] = json.dumps(payload, ensure_ascii=False)
        previous_analysis = None
        if previous is not None:
            previous_analysis = translate_analysis_ids(
                Analysis.model_validate(previous.metadata["analysis"]), aliases
            )
        provider_calls = []

        async def generate(messages, *, schema):
            if isinstance(self.provider, OpenAICompatibleProvider):
                # JSON-object mode needs the active schema in every full/focused prompt.
                messages = [dict(m) for m in messages]
                messages[0]["content"] += "\nReturn JSON using this schema:\n" + json.dumps(
                    schema, ensure_ascii=False
                )
            generated = await self.provider.generate(messages, schema)
            metadata = getattr(generated, "metadata", {})
            provider_calls.append(metadata)
            usage = metadata.get("usage", {})
            return {
                "message": {"content": json.dumps(generated, ensure_ascii=False)},
                "model": metadata.get("model", self.model),
                "prompt_eval_count": usage.get("input_tokens"),
                "eval_count": usage.get("output_tokens"),
            }

        phase_calls = []
        analysis = (
            await review_analysis(
                request, previous_analysis, phase_calls, generate, prompt_messages=messages
            )
            if previous_analysis is not None
            else await analyze_phase(request, messages, phase_calls, "evaluate", generate)
        )
        # First validate against the actual local sources, then restore canonical IDs.
        # Mapping is bijective; text, actor roles and quotation spans are never rewritten.
        validate_analysis(request, analysis)
        analysis = translate_analysis_ids(analysis, sources)
        validate_analysis(canonical, analysis)
        if previous_analysis is not None:
            previous_analysis = translate_analysis_ids(previous_analysis, sources)
        calls = [
            *(previous.metadata.get("calls", []) if previous else []),
            *[
                {**metadata, **phase}
                for metadata, phase in zip(provider_calls, phase_calls, strict=True)
            ],
        ]
        return EvaluationResult(
            is_mock=self.is_mock,
            findings=[
                Finding(
                    criterion_id=f.criterionId,
                    answer=f.answer,
                    explanation=f.reason,
                    message_ids=list(
                        dict.fromkeys(
                            [
                                *([f.evidenceId] if f.evidenceId else []),
                                *(e.messageId for e in f.evidence),
                            ]
                        )
                    ),
                    checked_message_ids=f.checkedMessageIds,
                    na_reason=f.reason if f.answer == "N/A" else None,
                )
                for f in analysis.results
            ],
            metadata={
                "summary": analysis.summary,
                "quotes": {f.criterionId: f.quote for f in analysis.results},
                "analysis": analysis.model_dump(mode="json"),
                "semanticValidation": {
                    "explicitApplicability": bool(analysis.applicability),
                    "reviewTargets": review_targets(request, previous_analysis)
                    if previous_analysis is not None
                    else {},
                    "expertAccuracyGuaranteed": False,
                },
                "calls": calls,
                "promptVersion": PROMPT_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "pipelineVersion": PIPELINE_VERSION,
                "checklistFingerprint": fingerprint([c.model_dump() for c in request.criteria]),
                "reviewRecommended": any(f.reviewRecommended for f in analysis.results),
                "scoreProvisional": any(f.reviewRecommended for f in analysis.results),
                "evidenceValidation": {
                    "idsAndQuotesValidated": True,
                    "rolesValidated": True,
                    "semanticRelevanceGuaranteed": False,
                },
                "draftResults": (
                    previous.metadata["analysis"]["results"]
                    if previous
                    else analysis.model_dump(mode="json")["results"]
                ),
                "criticChanges": [
                    {
                        "criterionId": before.criterionId,
                        "draftAnswer": before.answer,
                        "finalAnswer": after.answer,
                        "answerChanged": before.answer != after.answer,
                        "evidenceChanged": (before.evidenceId, before.quote, before.evidence)
                        != (after.evidenceId, after.quote, after.evidence),
                    }
                    for before in (previous_analysis.results if previous_analysis else [])
                    for after in analysis.results
                    if before.criterionId == after.criterionId
                ],
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
        if isinstance(self.evaluator, ProviderEvaluator) and "analysis" in result.metadata:
            # Disabling Critic must not permit a contradictory result to be persisted.
            request, _ = self.evaluator.request_messages(conversation, checklist)
            require_consistent_semantics(
                request, Analysis.model_validate(result.metadata["analysis"])
            )
        # The infrastructure is authoritative about whether mock mode was used.
        result.is_mock = self.evaluator.is_mock
        result.metadata["duration_seconds"] = round(perf_counter() - started, 6)
        return {
            **result.model_dump(mode="json"),
            **self.scorer.score(checklist, result),
            "stages": stages,
        }
