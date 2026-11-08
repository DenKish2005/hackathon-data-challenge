# Applicability and focused semantic review

The scorer remains the existing Decimal engine. The public result retains a
separate `applicability` decision for every active criterion. The compact model
wire puts that explicit status before each finding's answer, then parsing expands it:

```json
{
  "criterionId": "custom-rule",
  "status": "not_applicable",
  "reason": "The active N/A condition holds in the inspected record.",
  "messageIds": ["message-1"]
}
```

`not_applicable` requires that criterion's allowed `N/A` answer. `applicable` and
`uncertain` cannot exclude its weight with `N/A`; uncertainty requires review.
The active description and `naCondition` decide applicability. No conversation
IDs, labels, fixed eight-criterion answers or keyword-based customer decisions
are embedded in the evaluator.

The model's fresh output schema requires complete applicability coverage and
definition-scoped observations where guidance supplies them. Older stored results
remain readable without this additive field. A legacy provider result without
decisions remains provisional and is selected for review, rather than being
presented as a complete semantic assessment.

The validator detects observable internal contradictions: applicability versus
answer, explicit N/A conclusions versus the selected answer, definition-scoped
observations versus the judgment, uncited answered requests, and maximum original
consultation scores alongside unanswered requests. It does not infer answers from
the model's fallible observations. Contradictions must be corrected before final
persistence, including when Critic is disabled. A consistent but factually wrong
judgment can still pass; exact quotation is not a semantic relevance guarantee.

Reference guidance and its checks remain bound to complete definition
fingerprints, not IDs or titles. Editing a definition disables the old profile.
Generic applicability checks apply to arbitrary dynamic checklists. Clarification
and identification guidance distinguishes sufficient context and general
navigation from necessary clarification and actual customer-specific protected
acts. Consultation inventories exclude acknowledgments without new requests.

Critic selects conflicts, uncertain findings, N/A-bearing criteria, numeric
judgments and positive flags. This deliberately conservative selection can still
include most of a difficult rubric. It receives only selected definitions and
decision IDs/answers/statuses, with the full original transcript and explicit
review priorities. Verbose draft explanations, inventories and quotes are not
recirculated as assistant text; Critic rechecks the selected definitions against
the actual sources independently. The
application merges replacements by ID and retains unrelated validated findings.
Focused repairs preserve the applicability decisions and request inventory too.
Foundation prompts use short local message IDs; all references are strictly
validated against the unchanged text and roles, then mapped bijectively back to
canonical IDs for persistence and the API. This avoids repeating long hashes in
every applicability decision, quotation and inspected range.
Simple, internally consistent custom binary findings need no rewrite. Prompt,
schema, pipeline and adapter versions changed to invalidate stale caches.

## Reproducible bounded comparison

`python -m cqa.judge_benchmark` uses the real Foundation `Pipeline` and local
Ollama. It never downloads models. Files containing cases, labels, predictions,
raw responses and reports must be outside **every** Git worktree.

Create a private cases JSON with `cases`, each containing `id`, `request` (the
existing `EvaluationRequest`), and optional `channel`, `checklistId`, `sections`.
Keep expected labels in a separate private JSON mapping case IDs to lists of
`{criterionId, answer}`. The `run` command cannot read labels. The `compare`
command opens them only after predictions have been saved.

```powershell
$env:PYTHONPATH = 'C:\path\to\selected-source\src'
python -m cqa.judge_benchmark run `
  --cases 'C:\private\cases.json' `
  --output-dir 'C:\private\new-run' `
  --repeats 1 --max-evaluations 2 `
  --max-model-calls 12 --deadline-seconds 720

python -m cqa.judge_benchmark compare `
  --before 'C:\private\before.json' `
  --after 'C:\private\new-run\predictions.json' `
  --cases 'C:\private\cases.json' `
  --labels 'C:\private\labels.json' `
  --output 'C:\private\comparison.json'
```

The driver hard-limits selection to two cases, two repeats, four evaluations,
twelve generation invocations and 900 seconds. The example requests only two
evaluations within a shared 720-second budget. Each two_pass evaluation can need
up to six invocations including legitimate repairs. All remaining live
testing in one task must share one budget; do not reset the limits by launching
another run. Provider transport retries are disabled. Failed attempts remain in
the output, and partial predictions are saved individually.

For a prior code snapshot, invoke the **same driver file by absolute path** with
`PYTHONPATH` pointing to that snapshot's `src`, or normalize frozen real results
to its output record format. Record the code revision, model identity, generation
settings and provenance. Historical latency is observational, not an interleaved
performance experiment. Do not rerun an old baseline when suitable frozen results
already exist merely to increase sample size.

Comparison rejects changed input fingerprints, changed model/generation settings,
cached/mock repeats, duplicate criteria and incorrect stored scores. Accuracy and
score MAE use the first run per case so repeats do not overweight one example.
The report includes per-criterion confusion, N/A TP/FP/FN/TN/missing counts,
with different definitions separated even when their criterion IDs are reused,
coverage, failed attempts, fresh-repeat agreement, score ranges, calls and latency.
Unpaired labelled cases are listed explicitly. Small diagnostic samples and
provisional manual annotations do not establish general accuracy; report both
contradiction rejection and evaluation coverage.

API/frontend response fields and strict role/ID/exact-quote checks are preserved.
The new decisions and review targets are available in analysis/metadata; this
change does not add frontend review badges or modify infrastructure.
