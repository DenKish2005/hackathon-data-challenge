"""Definition-scoped consistency checks, never a replacement semantic classifier.

Model observations remain claims. Contradictions request a grounded correction;
this module never changes an answer or infers applicability from a conversation ID.
"""

import re

from cqa.prompts import GUIDANCE, profile

NA_ASSERTION = re.compile(
    r"(?:^|[.!?]\s+)(?:(?:следовательно|поэтому|thus|therefore)[,:]?\s+)?"
    r"(?:(?:выбранный|итоговый|final)\s+)?(?:ответ|оценка|answer|rating)\s*"
    r"(?:(?:должен\s+быть|должна\s+быть|should\s+be|must\s+be|is)\s*)?"
    r"[=:—-]?\s*[«\"']?N/A\b",
    re.IGNORECASE,
)

ANSWER_ASSERTION = re.compile(
    r"(?:^|[.!?]\s+)(?:(?:следовательно|поэтому|thus|therefore)[,:]?\s+)?"
    r"(?:(?:итогов(?:ый|ая)|выбранн(?:ый|ая)|final)\s+)?(?:ответ|оценка|answer|rating)\s*"
    r"(?:[:=—-]\s*|(?:is|должен быть)\s+)[«\"']?(N/A|Да|Нет|yes|no|\d+(?:\.\d+)?)"
    r"(?=[\s.!?,;»\"']|$)",
    re.IGNORECASE,
)
EXCLUDED_TIMING = re.compile(
    r"(?:должен|обязан|согласно правилу|порог|превыш\w*|укладыва\w*|менее|within|must|threshold)"
    r"[^.!?]{0,90}(?:3\s*мин|тр[её]х[ -]?мин|three[ -]?minute|3[ -]?minute)",
    re.IGNORECASE,
)
TIMING_EXCLUSION = re.compile(r"исключ|не примен|не учитыв|excluded|not appl|ignore", re.IGNORECASE)
FIRST_RESPONSE = re.compile(
    r"перв\w*\s+ответ|время\s+ответа|first[ -]response|initial reply", re.IGNORECASE
)


def semantic_issues(request, analysis):
    """Return observable internal conflicts, not assertions of expert accuracy."""
    issues = {}

    def add(cid, message):
        issues.setdefault(cid, []).append(message)

    decisions = {d.criterionId: d for d in analysis.applicability}
    for criterion, finding in (
        (c, r) for c in request.criteria for r in analysis.results if c.id == r.criterionId
    ):
        cid = criterion.id
        decision = decisions.get(cid)
        if decision:
            if decision.status == "not_applicable":
                if not criterion.naAllowed or finding.answer != "N/A":
                    add(cid, "Not-applicable decision requires an allowed N/A answer")
            elif finding.answer == "N/A":
                add(cid, "N/A contradicts an applicable or uncertain decision")
            if decision.status == "uncertain" and not finding.reviewRecommended:
                add(cid, "Uncertain applicability requires human review, not an N/A exclusion")
        if finding.answer != "N/A" and NA_ASSERTION.search(finding.reason):
            add(cid, "Explanation explicitly selects N/A but answer does not")
        for assertion in ANSWER_ASSERTION.finditer(finding.reason):
            claimed = assertion.group(1)
            if claimed.casefold() in {"да", "yes", "нет", "no", "n/a"}:
                claimed = {"да": "Да", "yes": "Да", "нет": "Нет", "no": "Нет", "n/a": "N/A"}[
                    claimed.casefold()
                ]
            else:
                claimed = float(claimed)
            if claimed != finding.answer:
                add(cid, "Explicit final answer in explanation disagrees with the selected answer")

        name = profile(criterion)
        if name == "management" and any(
            FIRST_RESPONSE.search(sentence)
            and EXCLUDED_TIMING.search(sentence)
            and not TIMING_EXCLUSION.search(sentence)
            for sentence in re.split(r"[.!?]\s*", finding.reason)
        ):
            add(
                cid,
                "Explanation applies the first-response timing rule "
                "excluded by the active definition",
            )
        checks = finding.checks
        expected = set(GUIDANCE[name][1]) if name else set()
        if decision and expected and not checks:
            add(cid, "Explicit applicability requires the supplied definition-scoped observations")
        if checks and set(checks) != expected:
            add(cid, "Observation fields do not match the active criterion definition")
            continue
        if not checks:
            continue
        if name == "needs":
            sufficient = checks["sufficientAtJoin"]
            clarified = checks["necessaryClarificationUsed"]
            if (finding.answer == "N/A") != sufficient:
                add(cid, "Clarification applicability contradicts sufficient initial context")
            if finding.answer == "Да" and (sufficient or not clarified):
                add(cid, "Positive clarification requires necessary information obtained and used")
        elif name == "identity":
            needed, verified = checks["verificationRequired"], checks["verifiedBeforeAction"]
            if (finding.answer == "N/A") != (not needed):
                add(cid, "Identification applicability contradicts the protected-act requirement")
            if needed and (finding.answer == "Да") != verified:
                add(cid, "Identification answer contradicts confirmation before the protected act")
        elif name == "consultation":
            if (finding.answer == "N/A") == checks["clientRequestFormulated"]:
                add(cid, "Consultation applicability contradicts a substantive client request")
        elif name == "contact" and finding.answer == "Да" and not all(checks.values()):
            add(cid, "Positive contact contradicts greeting/introduction observations")
        elif name == "closing":
            if finding.answer == "Да" and not (checks["summaryOrHelp"] and checks["goodbye"]):
                add(cid, "Positive closing requires both summary/help and an operator closing")
            if (finding.answer == "N/A") != checks["interruptionPreventedClosing"]:
                add(cid, "Closing applicability contradicts the observed opportunity to close")
        elif name == "severe" and (finding.answer == "Да") != checks["qualifyingAct"]:
            add(cid, "Severe answer contradicts the qualifying-act observation")

    for criterion in request.criteria:
        if profile(criterion) != "consultation":
            continue
        finding = next(r for r in analysis.results if r.criterionId == criterion.id)
        if finding.answer == max(criterion.scale) and any(
            r.resolution in {"unanswered", "partial"} for r in analysis.requests
        ):
            add(criterion.id, "Maximum consultation level conflicts with an unanswered request")
        if finding.answer == "N/A" and analysis.requests:
            add(criterion.id, "Consultation N/A conflicts with the substantive-request inventory")
        if any(r.resolution == "answered" and not r.operatorMessageIds for r in analysis.requests):
            add(criterion.id, "An answered request must identify an actual operator response")
    return {cid: "; ".join(dict.fromkeys(messages)) for cid, messages in issues.items()}


def review_targets(request, analysis):
    """Review conflicts and judgment/applicability risks; preserve supported simple findings."""
    issues = semantic_issues(request, analysis)
    decisions = {d.criterionId: d for d in analysis.applicability}
    findings = {r.criterionId: r for r in analysis.results}
    targets = {}
    for criterion in request.criteria:
        finding = findings[criterion.id]
        reasons = []
        if criterion.id in issues:
            reasons.append(issues[criterion.id])
        if criterion.id not in decisions:
            reasons.append("Legacy output has no explicit applicability decision")
        elif decisions[criterion.id].status == "uncertain":
            reasons.append("Applicability is uncertain")
        if finding.reviewRecommended or finding.uncertaintyNotes:
            reasons.append("Draft requests review of evidence or interpretation")
        if criterion.naAllowed:
            reasons.append("Recheck the active N/A condition before excluding or earning weight")
        if criterion.type == "scale":
            reasons.append("Recheck the selected level against the active scale descriptions")
        if criterion.type == "flag" and finding.answer == "Да":
            reasons.append("Positive flag requires an independent check of the qualifying act")
        if reasons:
            targets[criterion.id] = list(dict.fromkeys(reasons))
    return targets
