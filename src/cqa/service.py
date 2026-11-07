"""Strict checklist evaluation, evidence validation and durable evaluation history."""

import asyncio
import copy
import json
import math
import os
import re
import sqlite3
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cqa.normalization import NORMALIZATION_VERSION, normalize_messages
from cqa.prompts import (
    CRITIC_RULES as CRITIC_RULES,
)
from cqa.prompts import (
    GUIDANCE,
    PIPELINE_VERSION,
    PROMPT_VERSION,
    RULES,
    SCHEMA_VERSION,
    build_messages,
    critic_instruction,
    fingerprint,
    model_answers,
    profile,
    rubric_guidance,
    wire_answer,
)
from cqa.semantics import review_targets, semantic_issues


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Criterion(Strict):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    weight: float = Field(ge=0, le=1000)
    type: Literal["binary", "scale", "flag"]
    scale: list[float] = Field(default_factory=list, max_length=100)
    naAllowed: bool = False
    naCondition: str = ""

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.scale)) != len(self.scale) or not all(map(math.isfinite, self.scale)):
            raise ValueError("Ступени шкалы должны быть уникальными конечными числами")
        if self.type == "scale" and (not self.scale or min(self.scale) < 0 or max(self.scale) <= 0):
            raise ValueError("Числовая шкала должна содержать положительный максимум")
        if self.type == "flag" and (self.weight or self.naAllowed):
            raise ValueError("Флаг не имеет веса или N/A")
        if self.naAllowed and not self.naCondition.strip():
            raise ValueError("Укажите условие N/A")
        return self


class Message(Strict):
    id: str = Field(min_length=1, max_length=100)
    role: Literal["client", "operator", "bot", "system"]
    text: str = Field(max_length=15000)
    time: str


class EvaluationRequest(Strict):
    conversation_id: str = Field(min_length=1, max_length=200)
    language: Literal["RU", "KZ", "EN"]
    messages: list[Message] = Field(min_length=1, max_length=500)
    criteria: list[Criterion] = Field(min_length=1, max_length=50)
    version: int = Field(ge=1)
    force: bool = False
    context: dict = Field(default_factory=dict)
    audioObservations: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        for values in (self.messages, self.criteria):
            if len({x.id for x in values}) != len(values):
                raise ValueError("ID должны быть уникальны")
        if sum(len(m.text) for m in self.messages) > 120000:
            raise ValueError("Слишком длинный транскрипт")
        return self


class Evidence(Strict):
    messageId: str
    role: Literal["operator", "client", "bot", "system"]
    quote: str = Field(min_length=1, max_length=2000)
    relevance: str = Field(min_length=1, max_length=1000)


class Finding(Strict):
    criterionId: str
    answer: str | float
    reason: str = Field(min_length=10, max_length=3000)
    evidenceId: str
    quote: str = Field(max_length=2000)
    checkedMessageIds: list[str] = Field(min_length=1, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    evidenceBasis: Literal["direct", "context", "absence"] = "direct"
    checks: dict[str, bool] = Field(default_factory=dict)
    violationType: Literal["insult", "unauthorized_payment", "confidential_disclosure"] | None = (
        None
    )
    reviewRecommended: bool = False
    reviewReason: str = Field(default="", max_length=1500)
    uncertaintyNotes: list[str] = Field(default_factory=list, max_length=10)


class ClientRequest(Strict):
    messageId: str
    request: str = Field(min_length=1, max_length=250)
    operatorMessageIds: list[str] = Field(default_factory=list, max_length=20)
    resolution: Literal["answered", "partial", "next_step", "unanswered"]


class ApplicabilityDecision(Strict):
    criterionId: str
    status: Literal["applicable", "not_applicable", "uncertain"]
    reason: str = Field(min_length=10, max_length=600)
    messageIds: list[str] = Field(min_length=1, max_length=500)


class Analysis(Strict):
    # Additive for old stored results and clients. New model schemas require this field.
    applicability: list[ApplicabilityDecision] = Field(default_factory=list, max_length=50)
    results: list[Finding] = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1, max_length=3000)
    requests: list[ClientRequest] = Field(default_factory=list, max_length=20)


class GroundingError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(f"Criterion {cid}: {issue}" for cid, issue in issues.items()))


class ModelOutputError(ValueError):
    """Safe public message; raw response is available only to explicit private diagnostics."""

    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


def _courtesy_only(quote):
    normalized = re.sub(r"[\W_]+", " ", quote.casefold()).strip()
    return normalized in {
        "goodbye",
        "bye",
        "have a good day",
        "hello",
        "hi",
        "thank you",
        "thanks",
        "до свидания",
        "здравствуйте",
        "спасибо",
        "хорошего дня",
        "всего доброго",
        "сау болыңыз",
        "сау болыңыздар",
        "сәлеметсіз бе",
        "рақмет",
        "рахмет",
    }


def _review(finding, issue):
    """Self-reported observations are fallible; never turn them into facts or new answers."""
    finding.reviewRecommended = True
    finding.reviewReason = finding.reviewReason or "Self-check conflict: " + issue
    if issue not in finding.uncertaintyNotes and len(finding.uncertaintyNotes) < 10:
        finding.uncertaintyNotes.append(issue)
    return None


def _validate_finding(request, c, r, messages):
    allowed = c.scale if c.type == "scale" else ["Да", "Нет"]
    if r.answer not in [*allowed, *(["N/A"] if c.naAllowed else [])]:
        return "answer is outside the active rubric"
    if not r.reason.strip():
        return "nonempty reason required"
    checked = r.checkedMessageIds
    if len(set(checked)) != len(checked) or not checked or not set(checked) <= messages.keys():
        return "invalid checked message range"
    positive = r.answer == "Да" or (type(r.answer) in (float, int) and r.answer > 0)
    if r.evidenceBasis == "absence":
        if positive or r.evidenceId or r.quote or r.evidence:
            return "absence requires a non-positive/NA answer, no quotes, and an inspected range"
    else:
        if not r.quote.strip() or r.evidenceId not in messages:
            return (
                "non-absence findings require a primary ID and exact quote; for a justified "
                "missing action use evidenceBasis=absence, empty evidenceId/quote, "
                "and a checked range"
            )
        if r.quote not in messages[r.evidenceId].text:
            exact_ids = [m.id for m in request.messages if r.quote in m.text]
            return (
                f"primary quote is not in cited message {r.evidenceId}; "
                f"exact source IDs for this quote: {json.dumps(exact_ids)}. "
                "Inspect those sources and their roles/relevance; cite the correct source "
                "and include it in checkedMessageIds, or choose a new exact source quote"
            )
        if r.evidenceId not in checked:
            return (
                f"primary quote is exact in {r.evidenceId}, but that ID is missing from "
                "checkedMessageIds. Inspect that message and include its ID in the checked range"
            )
        for evidence in r.evidence:
            source = messages.get(evidence.messageId)
            if source is None or evidence.messageId not in checked:
                return "additional evidence ID is not in the inspected messages"
            if evidence.role != source.role:
                return "evidence role mismatch"
            if not evidence.quote.strip() or evidence.quote not in source.text:
                return "additional quote is not an exact source span"
            if not evidence.relevance.strip():
                return "evidence relevance is required"
        refs = [r.evidenceId, *(e.messageId for e in r.evidence)]
        if positive and not any(messages[mid].role == "operator" for mid in refs):
            return "positive operator behavior requires operator evidence"
        if c.type == "flag" and r.answer == "Да":
            if r.evidenceBasis != "direct" or messages[r.evidenceId].role != "operator":
                return "positive flag requires direct primary operator evidence"
            r.reviewRecommended = True
            r.reviewReason = (
                r.reviewReason or "Positive flag requires human review of the qualifying act."
            )
    name = profile(c)
    if name == "contact" and r.answer == "Да":
        first = next((m.id for m in request.messages if m.role == "operator"), None)
        if r.evidenceId != first:
            return "positive contact must cite the first human reply"
    if name == "severe" and r.answer == "Да":
        if not r.violationType:
            return "severe violation requires an identified qualifying act (violationType)"
        if _courtesy_only(r.quote):
            return "a courtesy-only quote does not support a severe violation"
    if name == "identity" and r.answer == "Нет":
        r.reviewRecommended = True
        r.reviewReason = r.reviewReason or (
            "Review the verification requirement and protected act; a missing check alone "
            "does not establish a severe violation."
        )
    if r.checks:
        expected = set(GUIDANCE[name][1]) if name else set()
        if set(r.checks) != expected:
            return _review(r, "observations do not match the active criterion definition")
        checks = r.checks
        if name == "needs":
            if r.answer == "N/A" and not checks["sufficientAtJoin"]:
                return _review(r, "N/A contradicts insufficient initial context")
            if r.answer == "Да" and (
                checks["sufficientAtJoin"] or not checks["necessaryClarificationUsed"]
            ):
                return _review(r, "YES requires necessary clarification obtained and used")
            if r.answer == "Нет" and checks["sufficientAtJoin"]:
                return _review(
                    r, "NO contradicts sufficient initial context; inspect N/A applicability"
                )
        if name == "identity":
            needed, confirmed = checks["verificationRequired"], checks["verifiedBeforeAction"]
            if (
                (r.answer == "N/A" and needed)
                or (r.answer == "Да" and not (needed and confirmed))
                or (r.answer == "Нет" and (not needed or confirmed))
            ):
                return _review(r, "identity answer contradicts verification observations")
        if name == "consultation" and r.answer == "N/A" and checks["clientRequestFormulated"]:
            return _review(r, "consultation N/A contradicts an already formulated client request")
        if name == "contact" and r.answer == "Да":
            first = next((m.id for m in request.messages if m.role == "operator"), None)
            if not all(checks.values()) or r.evidenceId != first:
                return _review(
                    r, "contact requires greeting and introduction in the first human reply"
                )
        if name == "closing":
            if r.answer == "Да" and not (checks["summaryOrHelp"] and checks["goodbye"]):
                return _review(r, "closing YES requires summary/help AND goodbye")
            if r.answer == "N/A" and not checks["interruptionPreventedClosing"]:
                return _review(
                    r, "closing N/A requires interruption preventing a closing opportunity"
                )
            if r.answer == "Нет" and checks["interruptionPreventedClosing"]:
                return _review(r, "closing NO contradicts an interruption preventing closing")
        if name == "severe" and (r.answer == "Да") != checks["qualifyingAct"]:
            return _review(r, "severe answer contradicts the observed qualifying act")
    if r.uncertaintyNotes or r.reviewReason.strip():
        r.reviewRecommended = True
    if request.context.get("incomplete") is True:
        r.reviewRecommended = True
        r.reviewReason = r.reviewReason or "Conversation context is marked incomplete."
    return None


def validate_analysis(request, analysis):
    criteria = {c.id: c for c in request.criteria}
    messages = {m.id: m for m in request.messages}
    if analysis.applicability:
        if len(analysis.applicability) != len(criteria) or {
            d.criterionId for d in analysis.applicability
        } != set(criteria):
            raise ValueError("Exactly one applicability decision per active criterion is required")
        for decision in analysis.applicability:
            if (
                len(set(decision.messageIds)) != len(decision.messageIds)
                or not set(decision.messageIds) <= messages.keys()
            ):
                raise GroundingError({decision.criterionId: "Invalid applicability source IDs"})
    for item in analysis.requests:
        if item.messageId not in messages or messages[item.messageId].role != "client":
            raise ValueError("Request inventory must reference actual client messages")
        if any(
            mid not in messages or messages[mid].role != "operator"
            for mid in item.operatorMessageIds
        ):
            raise ValueError("Request inventory answers must reference actual operator messages")
    if len(analysis.results) != len(criteria) or {r.criterionId for r in analysis.results} != set(
        criteria
    ):
        raise ValueError("Нужен ровно один результат для каждого критерия")
    issues = {
        r.criterionId: issue
        for r in analysis.results
        if (issue := _validate_finding(request, criteria[r.criterionId], r, messages))
    }
    if issues:
        raise GroundingError(issues)
    for decision in analysis.applicability:
        if decision.status == "uncertain":
            finding = next(r for r in analysis.results if r.criterionId == decision.criterionId)
            _review(finding, "Applicability cannot be established from the supplied record")
    for result in analysis.results:
        criterion = criteria[result.criterionId]
        if profile(criterion) == "consultation" and analysis.requests:
            if result.answer == max(criterion.scale) and any(
                r.resolution == "unanswered" for r in analysis.requests
            ):
                _review(
                    result, "Maximum consultation score conflicts with an unresolved client request"
                )
            if result.answer == "N/A":
                _review(
                    result, "Consultation N/A conflicts with the listed substantive client requests"
                )
    for cid, issue in semantic_issues(request, analysis).items():
        _review(next(r for r in analysis.results if r.criterionId == cid), issue)
    if not analysis.applicability:
        for result in analysis.results:
            _review(result, "Legacy result has no explicit applicability decision")
    return analysis


def require_consistent_semantics(request, analysis):
    issues = semantic_issues(request, analysis)
    if issues:
        raise GroundingError(issues)
    return analysis


def translate_analysis_ids(analysis, mapping):
    """Translate validated local message references without moving quotations or changing roles."""
    translated = analysis.model_copy(deep=True)
    for decision in translated.applicability:
        decision.messageIds = [mapping[mid] for mid in decision.messageIds]
    for finding in translated.results:
        if finding.evidenceId:
            finding.evidenceId = mapping[finding.evidenceId]
        finding.checkedMessageIds = [mapping[mid] for mid in finding.checkedMessageIds]
        for evidence in finding.evidence:
            evidence.messageId = mapping[evidence.messageId]
    for item in translated.requests:
        item.messageId = mapping[item.messageId]
        item.operatorMessageIds = [mapping[mid] for mid in item.operatorMessageIds]
    return translated


def merge_analysis(request, base, replacement, selected):
    """Merge only selected findings/decisions, retaining immutable unrelated Draft results."""
    findings = {r.criterionId: r for r in replacement.results}
    decisions = {d.criterionId: d for d in replacement.applicability}
    previous_decisions = {d.criterionId: d for d in base.applicability}
    return Analysis(
        summary=base.summary,
        results=[findings.get(r.criterionId, r) for r in base.results],
        applicability=[
            decisions.get(c.id, previous_decisions.get(c.id))
            for c in request.criteria
            if c.id in decisions or c.id in previous_decisions
        ],
        requests=replacement.requests
        if "requests" in replacement.model_fields_set
        and any(profile(c) == "consultation" for c in selected)
        else base.requests,
    )


def inherit_prompt_context(messages, template):
    """Keep Foundation channel/checklist metadata in focused prompts and repairs."""
    if template is None:
        return messages
    payload = json.loads(messages[1]["content"])
    original = json.loads(template[1]["content"])["evaluation"]
    payload["evaluation"].update(
        {key: original[key] for key in ("channel", "checklist_id", "sections") if key in original}
    )
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False)
    return messages


async def review_analysis(request, draft, calls, generate, *, prompt_messages=None):
    targets = review_targets(request, draft)
    if not targets:
        return require_consistent_semantics(request, draft)
    focused = request.model_copy(
        update={"criteria": [c for c in request.criteria if c.id in targets]}
    )
    partial = draft.model_copy(
        update={
            "results": [r for r in draft.results if r.criterionId in targets],
            "applicability": [d for d in draft.applicability if d.criterionId in targets],
        }
    )
    decisions = {d.criterionId: d.status for d in partial.applicability}
    draft_decisions = [
        {
            "criterionId": r.criterionId,
            "answer": wire_answer(r.answer),
            "applicability": decisions.get(r.criterionId, "legacy_unspecified"),
        }
        for r in partial.results
    ]
    messages = inherit_prompt_context(build_messages(focused), prompt_messages)
    messages.extend(
        [
            {
                "role": "user",
                "content": critic_instruction(focused.criteria)
                + "\nReview priorities: "
                + json.dumps(targets, ensure_ascii=False)
                + "\nPrior decisions (claims, not facts): "
                + json.dumps(draft_decisions, ensure_ascii=False)
                + "\nReassess independently from the original transcript. "
                "Do not inherit an earlier explanation, request inventory or quotation.",
            },
        ]
    )
    corrected = await analyze_phase(focused, messages, calls, "critic", generate, partial)
    final = merge_analysis(request, draft, corrected, focused.criteria)
    final.summary = (
        corrected.summary
        if len(targets) == len(request.criteria)
        else "Повторно проверены критерии " + ", ".join(targets) + ": " + corrected.summary
    )
    validate_analysis(request, final)
    return require_consistent_semantics(request, final)


def score(criteria, results):
    earned = Decimal(0)
    available = Decimal(0)
    critical = False
    by_id = {r.criterionId: r for r in results}
    for c in criteria:
        answer = by_id[c.id].answer
        if c.type == "flag":
            critical |= answer == "Да"
        elif answer != "N/A":
            weight = Decimal(str(c.weight))
            available += weight
            normalized = (
                (Decimal(str(answer)) / Decimal(str(max(c.scale))))
                if c.type == "scale"
                else Decimal(int(answer == "Да"))
            )
            earned += weight * normalized
    total = (
        float((earned * 100 / available).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if available
        else None
    )
    return {"score": total, "critical": critical}


class Store:
    def __init__(self, path=None):
        self.path = path or os.getenv("CQA_DB", ".runtime/cqa.sqlite3")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS evaluations "
                "(id TEXT PRIMARY KEY, cache_key TEXT, body TEXT)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS eval_cache ON evaluations(cache_key)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def cached(self, key):
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM evaluations WHERE cache_key=? ORDER BY rowid DESC LIMIT 1", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, key, body):
        with self.connect() as db:
            db.execute(
                "INSERT INTO evaluations VALUES (?,?,?)",
                (body["evaluationId"], key, json.dumps(body, ensure_ascii=False)),
            )

    def history(self, conversation_id):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM evaluations ORDER BY rowid DESC").fetchall()
        return [
            body
            for row in rows
            if (body := json.loads(row[0]))["conversation_id"] == conversation_id
        ]


async def analyze_phase(request, messages, calls, phase, generate, analysis=None):
    """Shared bounded generation/grounding repair for legacy and Foundation adapters."""
    pending = None
    repair_feedback = ""
    for attempt in range(3):
        focused = (
            request
            if not pending
            else request.model_copy(
                update={"criteria": [c for c in request.criteria if c.id in pending]}
            )
        )
        call_started = time.perf_counter()
        call_messages = messages
        if pending:
            # A genuinely focused request must not carry the full old rubric
            # and invalid assistant answer, which can anchor the model to it.
            call_messages = inherit_prompt_context(build_messages(focused), messages)
            call_messages.append({"role": "user", "content": repair_feedback})
            if phase == "critic":
                call_messages.append(
                    {"role": "user", "content": critic_instruction(focused.criteria)}
                )
        response = await generate(call_messages, schema=analysis_schema(focused))
        calls.append(
            {
                "phase": phase,
                "repair": attempt > 0,
                "targeted": bool(pending),
                "criterionIds": [c.id for c in focused.criteria],
                "durationSeconds": round(time.perf_counter() - call_started, 3),
                **{
                    k: response.get(k)
                    for k in (
                        "model",
                        "prompt_eval_count",
                        "eval_count",
                        "total_duration",
                        "httpAttempts",
                    )
                },
            }
        )
        raw = response["message"]["content"]
        try:
            candidate = parse_analysis(raw, focused)
            if pending:
                validate_analysis(focused, candidate)
                candidate = merge_analysis(request, analysis, candidate, focused.criteria)
            analysis = candidate
            validate_analysis(request, analysis)
            if phase == "critic":
                require_consistent_semantics(request, analysis)
            calls[-1]["validated"] = True
        except (ValueError, KeyError) as exc:
            calls[-1]["validated"] = False
            calls[-1]["validationIssue"] = (
                "grounding" if isinstance(exc, GroundingError) else "structure"
            )
            if attempt == 2:
                raise ValueError("Модель не вернула проверяемую оценку после исправлений") from exc
            # Only a parsed result with criterion-specific grounding issues
            # permits a focused repair. Otherwise repair the complete JSON.
            if isinstance(exc, GroundingError) and analysis is not None:
                pending = set(exc.issues)
                feedback = (
                    "Repair ONLY these criterion IDs: "
                    + json.dumps(sorted(pending))
                    + ". "
                    + str(exc)
                    + ". Return results for exactly these IDs and a summary. "
                    "Preserve other valid findings; the application merges them."
                )
            else:
                # Invalid focused JSON does not discard the already valid draft.
                feedback = (
                    "Repair the JSON for "
                    + (json.dumps(sorted(pending)) if pending else "ALL active criteria")
                    + ". Return only the requested findings and a summary. "
                    "Use the schema and exact transcript evidence."
                )
            if pending:
                repair_feedback = feedback
            else:
                messages.extend(
                    [
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": feedback},
                    ]
                )
            continue
        break
    return analysis


class Evaluator:
    def __init__(self, store=None, transport=None):
        self.store = store or Store()
        self.model = os.getenv("CQA_MODEL", "qwen3:4b")
        if ":cloud" in self.model.lower() or self.model.lower().endswith("-cloud"):
            raise ValueError(
                "Cloud model tags are disabled for customer transcripts; use a local model"
            )
        self.url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.transport = transport
        concurrency = int(os.getenv("CQA_CONCURRENCY", "1"))
        if concurrency < 1:
            raise ValueError("CQA_CONCURRENCY должна быть положительной")
        self.semaphore = asyncio.Semaphore(concurrency)
        self.context_size = int(os.getenv("CQA_NUM_CTX", "65536"))
        if self.context_size < 8192:
            raise ValueError("CQA_NUM_CTX должна быть не меньше 8192")
        self.output_limit = int(os.getenv("CQA_NUM_PREDICT", "5000"))
        seed = os.getenv("CQA_SEED", "42")
        self.seed = None if seed.lower() in ("", "none") else int(seed)
        self.timeout = float(os.getenv("CQA_TIMEOUT", "600"))
        verify_sensitive = os.getenv("CQA_VERIFY_SENSITIVE", "true").lower()
        if verify_sensitive not in ("true", "false"):
            raise ValueError("CQA_VERIFY_SENSITIVE must be true or false")
        self.verify_sensitive = verify_sensitive == "true"
        if self.output_limit < 1 or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("CQA_NUM_PREDICT and CQA_TIMEOUT must be positive")

    def settings(self):
        return {
            "temperature": 0,
            "seed": self.seed,
            "num_ctx": self.context_size,
            "num_predict": self.output_limit,
            "think": False,
            "timeout": self.timeout,
            "verify_sensitive": self.verify_sensitive,
        }

    def check_context(self, messages, schema=None):
        # UTF-8 bytes conservatively bound message tokens. `format` is a separate
        # sampler grammar, not text injected by this client into the chat context.
        # Reserve the output allowance and template framing, never truncate messages.
        prompt_bytes = len(json.dumps(messages, ensure_ascii=False).encode())
        if prompt_bytes + self.output_limit + 1024 > self.context_size:
            raise ValueError(
                "Текст с чек-листом превышает безопасный контекст модели. "
                "Сократите запрос или увеличьте CQA_NUM_CTX при наличии памяти. "
                "Оценка усечённого транскрипта не выполняется."
            )

    async def generate(self, messages, *, schema=None):
        schema = schema or Analysis.model_json_schema()
        self.check_context(messages, schema)
        try:
            # HTTP read timeouts reset on keep-alive bytes. Also bound the whole
            # generation/retry operation so a slow stream cannot wait indefinitely.
            async with asyncio.timeout(self.timeout):
                return await self._generate(messages, schema)
        except TimeoutError as exc:
            raise httpx.ReadTimeout("Ollama generation deadline exceeded") from exc

    async def _generate(self, messages, schema):
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, trust_env=False, follow_redirects=False
        ) as client:
            for attempt in range(3):
                response = await client.post(
                    self.url + "/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "think": False,
                        "format": schema,
                        "messages": messages,
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.context_size,
                            "num_predict": self.output_limit,
                            **({"seed": self.seed} if self.seed is not None else {}),
                        },
                    },
                )
                if response.status_code in (429, 503) and attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
                    raise ValueError("Ollama вернула некорректный ответ")
                if data.get("done_reason") == "length":
                    raise ModelOutputError(
                        "Ответ модели оборван лимитом токенов; результат не сохранён", data
                    )
                reported_tokens = data.get("prompt_eval_count")
                if (
                    isinstance(reported_tokens, int)
                    and reported_tokens + self.output_limit >= self.context_size
                ):
                    raise ValueError("Ollama reported input too close to the safe context limit")
                if not isinstance(data.get("message", {}).get("content"), str):
                    raise ValueError("Ollama вернула ответ без текста оценки")
                return {**data, "httpAttempts": attempt + 1}

    async def evaluate(self, request):
        started = time.perf_counter()
        # Normalize the browser request before hashing, inference and quote validation.
        # Returning `messages` when changed uses the existing App.applyEvaluation spread
        # to synchronize displayed text without editing frontend files.
        messages_normalized, changes = normalize_messages(request.messages)
        request = request.model_copy(update={"messages": messages_normalized})
        content = request.model_dump(exclude={"force"})
        checklist_hash = fingerprint([c.model_dump() for c in request.criteria])
        key = fingerprint(
            {
                "input": content,
                "model": self.model,
                "endpoint": self.url,
                "settings": self.settings(),
                "prompt": RULES,
                "critic": critic_instruction(request.criteria),
                "referenceGuidance": rubric_guidance(request.criteria),
                "promptVersion": PROMPT_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "schema": analysis_schema(request),
                "pipeline": PIPELINE_VERSION,
                "normalization": NORMALIZATION_VERSION,
            }
        )
        async with self.semaphore:
            if not request.force and (cached := self.store.cached(key)):
                response = {**cached, "cached": True}
                if changes:
                    response.update(
                        messages=[m.model_dump() for m in request.messages],
                        normalization={"version": NORMALIZATION_VERSION, "changes": changes},
                    )
                else:
                    response.pop("normalization", None)
                    response.pop("messages", None)
                response["requestDurationSeconds"] = round(time.perf_counter() - started, 3)
                return response
            messages = build_messages(request)
            calls = []
            analysis = None
            draft = None
            analysis = await analyze_phase(request, messages, calls, "evaluate", self.generate)
            draft = analysis.model_copy(deep=True)
            analysis = await review_analysis(request, draft, calls, self.generate)
            critic_final = {r.criterionId: r.model_copy(deep=True) for r in analysis.results}
            risk_review = await self._review_sensitive(request, analysis, calls)
            require_consistent_semantics(request, analysis)
            critic_changes = [
                {
                    "criterionId": r.criterionId,
                    "draftAnswer": r.answer,
                    "finalAnswer": critic_final[r.criterionId].answer,
                    "answerChanged": r.answer != critic_final[r.criterionId].answer,
                    "evidenceChanged": (r.evidenceId, r.quote, r.evidence)
                    != (
                        critic_final[r.criterionId].evidenceId,
                        critic_final[r.criterionId].quote,
                        critic_final[r.criterionId].evidence,
                    ),
                }
                for r in draft.results
            ]
            actual = calls[-1].get("model") or self.model
            body = {
                "evaluationId": str(uuid4()),
                "conversation_id": request.conversation_id,
                "createdAt": datetime.now(UTC).isoformat(),
                "model": actual,
                "requestedModel": self.model,
                "inputHash": key,
                "checklistVersion": request.version,
                "checklistFingerprint": checklist_hash,
                "criteriaSnapshot": [c.model_dump() for c in request.criteria],
                **analysis.model_dump(),
                **score(request.criteria, analysis.results),
                "tokens": sum(
                    (c.get("eval_count") or 0) + (c.get("prompt_eval_count") or 0) for c in calls
                ),
                "passes": len(calls),
                "cached": False,
                "promptVersion": PROMPT_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "pipelineVersion": PIPELINE_VERSION,
                "generationSettings": self.settings(),
                "usage": calls,
                "draftResults": draft.model_dump()["results"],
                "criticChanges": critic_changes,
                "riskReview": risk_review,
                "reviewRecommended": any(r.reviewRecommended for r in analysis.results),
                "scoreProvisional": any(r.reviewRecommended for r in analysis.results),
                "evidenceValidation": {
                    "idsAndQuotesValidated": True,
                    "rolesValidated": True,
                    "semanticRelevanceGuaranteed": False,
                },
                "durationSeconds": round(time.perf_counter() - started, 3),
            }
            if changes:
                body.update(
                    messages=[m.model_dump() for m in request.messages],
                    normalization={"version": NORMALIZATION_VERSION, "changes": changes},
                )
            self.store.save(key, body)
            return body

    async def _review_sensitive(self, request, analysis, calls):
        """One independent check on an original privacy risk; never infer a breach from C3 alone."""
        by_id = {r.criterionId: r for r in analysis.results}
        identity = next((c for c in request.criteria if profile(c) == "identity"), None)
        severe = next((c for c in request.criteria if profile(c) == "severe"), None)
        if (
            not self.verify_sensitive
            or not identity
            or not severe
            or by_id[identity.id].answer != "Нет"
            or by_id[severe.id].answer != "Нет"
        ):
            return {"status": "not_triggered"}
        focused = request.model_copy(update={"criteria": [severe]})
        messages = build_messages(focused)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Independent sensitive-data review. An earlier judgement reported missing "
                    "verification. That is NOT proof of a severe violation. Independently inspect "
                    "actual confidential disclosure, insults or unauthorized paid-service offers. "
                    "YES requires a direct qualifying quote; otherwise NO. Do not infer outside "
                    "verification or unseen acts. Return only this criterion."
                ),
            }
        )
        started = time.perf_counter()
        call = {
            "phase": "risk_review",
            "repair": False,
            "targeted": True,
            "criterionIds": [severe.id],
            "validated": False,
        }
        calls.append(call)
        try:
            response = await self.generate(messages, schema=analysis_schema(focused))
            call.update(
                {
                    k: response.get(k)
                    for k in (
                        "model",
                        "prompt_eval_count",
                        "eval_count",
                        "total_duration",
                        "httpAttempts",
                    )
                }
            )
            candidate = parse_analysis(response["message"]["content"], focused)
            validate_analysis(focused, candidate)
            replacement = candidate.results[0]
            previous = by_id[severe.id].answer
            merged = analysis.model_copy(deep=True)
            merged.results = [
                replacement if r.criterionId == severe.id else r for r in merged.results
            ]
            validate_analysis(request, merged)
            analysis.results = merged.results
            call["validated"] = True
            return {
                "status": "completed",
                "criterionId": severe.id,
                "previousAnswer": previous,
                "finalAnswer": replacement.answer,
                "answerChanged": previous != replacement.answer,
            }
        except (ValueError, KeyError, httpx.HTTPError) as exc:
            call["errorType"] = type(exc).__name__
            _review(
                by_id[severe.id],
                "Independent sensitive-data review could not be grounded; human review required",
            )
            return {
                "status": "review_required",
                "criterionId": severe.id,
                "errorType": type(exc).__name__,
            }
        finally:
            call["durationSeconds"] = round(time.perf_counter() - started, 3)


def analysis_schema(request):
    """Compact active enums; validate_analysis enforces each criterion's own answer set.

    Avoid repeating the entire finding schema for every criterion: this reduces
    grammar/context overhead on a laptop without weakening runtime validation.
    """
    schema = Analysis.model_json_schema()
    schema["required"] = [*schema["required"], "applicability"]
    decisions = []
    ids = [m.id for m in request.messages]
    for criterion in request.criteria:
        decision = copy.deepcopy(schema["$defs"]["ApplicabilityDecision"])
        decision["properties"]["criterionId"] = {"const": criterion.id}
        decision["properties"]["status"] = {
            "enum": ["applicable", "uncertain"]
            + (["not_applicable"] if criterion.naAllowed else [])
        }
        decision["properties"]["messageIds"].update(
            items={"enum": ids}, maxItems=len(ids), uniqueItems=True
        )
        decisions.append(decision)
    schema["properties"]["applicability"].update(minItems=len(decisions), maxItems=len(decisions))
    if len(decisions) == 1:
        schema["properties"]["applicability"]["items"] = decisions[0]
    else:
        schema["properties"]["applicability"].pop("items", None)
        schema["properties"]["applicability"]["prefixItems"] = decisions
    finding = schema["$defs"].pop("Finding")
    ids = [m.id for m in request.messages]
    finding["properties"]["evidenceId"] = {"enum": ["", *ids]}
    finding["properties"]["checkedMessageIds"].update(
        items={"enum": ids}, maxItems=len(ids), uniqueItems=True
    )
    # Bound free collections to the actual input, rather than letting a small model
    # repeat IDs/observations until the output budget is exhausted.
    finding["properties"]["evidence"]["maxItems"] = min(4, len(ids))
    finding["properties"]["reason"]["maxLength"] = 600
    finding["properties"]["quote"]["maxLength"] = 300
    finding["properties"]["uncertaintyNotes"]["maxItems"] = 2
    finding["properties"]["uncertaintyNotes"]["items"]["maxLength"] = 250
    schema["$defs"]["Evidence"]["properties"]["messageId"] = {"enum": ids}
    schema["$defs"]["Evidence"]["properties"]["quote"]["maxLength"] = 300
    schema["$defs"]["Evidence"]["properties"]["relevance"]["maxLength"] = 200
    schema["properties"]["summary"]["maxLength"] = 500
    if any(profile(c) == "consultation" for c in request.criteria):
        schema["required"] = [*schema["required"], "requests"]
    client_ids = [m.id for m in request.messages if m.role == "client"]
    schema["$defs"]["ClientRequest"]["properties"]["messageId"] = {"enum": client_ids or [""]}
    schema["$defs"]["ClientRequest"]["properties"]["operatorMessageIds"].update(
        items={"enum": [m.id for m in request.messages if m.role == "operator"] or [""]},
        maxItems=min(20, sum(m.role == "operator" for m in request.messages)),
        uniqueItems=True,
    )
    if not client_ids:
        schema["properties"]["requests"]["maxItems"] = 0
    # Factor shared field definitions to keep per-criterion answer/check constraints
    # without repeating long schemas. Type-specific enums prevent YES on numeric scales.
    shared = {}
    for key, value in finding["properties"].items():
        if key not in ("criterionId", "answer", "checks"):
            name = "Finding_" + key
            schema["$defs"][name] = value
            shared[key] = {"$ref": "#/$defs/" + name}
    variants = []
    for criterion in request.criteria:
        values = criterion.scale if criterion.type == "scale" else ["Да", "Нет"]
        names = GUIDANCE[profile(criterion)][1] if profile(criterion) else []
        properties = {
            "criterionId": {"enum": [criterion.id]},
            "checks": {
                "type": "object",
                "properties": {n: {"type": "boolean"} for n in names},
                "required": names,
                "additionalProperties": False,
            },
            "reason": shared["reason"],
            "answer": {"enum": model_answers(criterion)},
            **{k: v for k, v in shared.items() if k != "reason"},
        }
        required = list(
            dict.fromkeys(
                [
                    *finding["required"],
                    "evidenceBasis",
                    "reviewRecommended",
                    "uncertaintyNotes",
                ]
            )
        )
        if names:
            required.append("checks")
        # A non-absence branch cannot emit empty primary evidence. The absence branch
        # permits only non-positive/NA answers and explicit empty quote placeholders.
        direct = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        direct["properties"]["evidenceId"] = {"enum": ids}
        direct["properties"]["quote"] = {"type": "string", "minLength": 1, "maxLength": 300}
        direct["properties"]["evidenceBasis"] = {"enum": ["direct", "context"]}
        absent_answers = [
            v
            for v in [*values, *(["N/A"] if criterion.naAllowed else [])]
            if v in ("Нет", "N/A", 0)
        ]
        modes = []
        positive_answers = [
            v for v in values if v == "Да" or (isinstance(v, (int, float)) and v > 0)
        ]
        operator_ids = [m.id for m in request.messages if m.role == "operator"]
        if positive_answers and operator_ids:
            positive = copy.deepcopy(direct)
            positive["properties"]["answer"] = {"enum": [wire_answer(v) for v in positive_answers]}
            positive["properties"]["evidenceId"] = {
                "enum": operator_ids[:1] if profile(criterion) == "contact" else operator_ids
            }
            if criterion.type == "flag":
                positive["properties"]["evidenceBasis"] = {"const": "direct"}
                if profile(criterion) == "severe":
                    positive["properties"]["violationType"] = {
                        "enum": ["insult", "unauthorized_payment", "confidential_disclosure"]
                    }
                    positive["required"] = [*positive["required"], "violationType"]
            modes.append(positive)
        if absent_answers:
            negative = copy.deepcopy(direct)
            negative["properties"]["answer"] = {"enum": [wire_answer(v) for v in absent_answers]}
            modes.append(negative)
            absent = copy.deepcopy(direct)
            absent["properties"].update(
                answer={"enum": [wire_answer(v) for v in absent_answers]},
                evidenceId={"const": ""},
                quote={"const": ""},
                evidenceBasis={"const": "absence"},
                evidence={"type": "array", "maxItems": 0},
            )
            modes.append(absent)
        if not modes:
            raise ValueError(
                "No supported answer has possible operator evidence in this transcript"
            )
        variants.append({"anyOf": modes} if len(modes) > 1 else modes[0])
    result_schema = schema["properties"]["results"]
    result_schema.update(minItems=len(variants), maxItems=len(variants))
    if len(variants) == 1:
        result_schema["items"] = variants[0]
    else:
        result_schema.pop("items", None)
        result_schema["prefixItems"] = variants
    return schema


def parse_analysis(raw, request):
    """Normalize only exact legal model-wire score strings; public validation stays strict."""
    data = json.loads(raw)
    criteria = {c.id: c for c in request.criteria}
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        for result in data["results"]:
            if not isinstance(result, dict) or not isinstance(result.get("criterionId"), str):
                continue
            criterion = criteria.get(result["criterionId"])
            if criterion and criterion.type == "scale" and isinstance(result.get("answer"), str):
                legal = {wire_answer(v): v for v in criterion.scale}
                if result["answer"] in legal:
                    result["answer"] = legal[result["answer"]]
    analysis = Analysis.model_validate(data)
    # Keep the legacy field, but never publish a generated number as calibrated confidence.
    for finding in analysis.results:
        finding.confidence = None
    return analysis
