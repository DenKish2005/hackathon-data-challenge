# AI hardening integration

The active path remains `/api/evaluate` → `cqa.service.Evaluator` → Ollama draft →
mandatory Critic → validation → existing Decimal scorer → existing SQLite Store.
The foundation queue/provider pipeline is not activated. No frontend source is changed.

## Rubric changes

Send the current criteria in the existing `EvaluationRequest`; no source edits are needed.
IDs, count, order, weights, scales and N/A conditions are configurable. Supported answer
types remain binary, numeric scale and independent flag. Arbitrary categorical labels
are not added to the public contract.

`prompts.py` supplies generic rules and optional definition-matched guidance.
Frozen reference fingerprints include title, description, type, scale and N/A conditions;
they exclude IDs and weights. This deliberately conservative matching never applies an
old profile based only on a reused ID/title. Rewording a definition disables the extra
reference guidance; the active definition remains authoritative. This includes C6's
current exclusion of the three-minute first-response threshold.

Both draft and Critic receive the active rubric. Structured output binds the result
count and active ID/answer enums; Python validates the answer against its own criterion.
The compact schema avoids repeating the complete finding definition per criterion.
The model-only transport uses string answers for every type to avoid mixed number/N/A
generation bias in a small model. Only exact configured score strings are converted
back into numeric API answers. Public `validate_analysis` still rejects numeric strings;
illegal scores are never coerced into another answer. Ordered schema tuples prevent
duplicated criteria, and separate evidence branches require explicit absence metadata
when no quote is supplied. These are output-format constraints, not predetermined decisions.

## Evidence and review

Existing `criterionId`, `answer`, `reason`, `evidenceId`, `quote`,
`checkedMessageIds` and `confidence` remain. Additive fields:

| Field | Meaning |
| --- | --- |
| `evidence` | Additional `{messageId, role, quote, relevance}` records |
| `evidenceBasis` | `direct`, `context`, or `absence` |
| `checks` | Optional definition-scoped boolean review observations |
| `violationType` | Qualifying act for a positive original severe-violation finding |
| `reviewRecommended`, `reviewReason`, `uncertaintyNotes` | Review metadata, not new rubric answers |

IDs, roles, exact source substrings and checked ranges are validated. Positive human
performance needs operator evidence. Positive flags require direct primary operator
evidence. Original severe findings require a qualifying act; courtesy-only quotes are
rejected as obviously insufficient. This is a narrow contradiction check, not a semantic
classifier. A valid quote or same-model Critic does not guarantee correct interpretation.
Positive flags recommend human review.

Absence-based non-positive/N/A findings may contain `evidenceId=""`, `quote=""` and
`evidence=[]`, with a specific reason and nonempty inspected range. Existing frontend
code safely has no evidence link in this case. The review explanation remains visible;
a dedicated checked-range presentation is a frontend enhancement.

Self-check booleans are model reports, not trusted facts. A contradiction between these
optional observations and the answer sets review metadata without changing the answer.
The mandatory Critic sees these warnings. This avoids forcing a decision merely to agree
with another fallible model field. Mechanically invalid IDs, roles, quotes, answers, or
unsupported positive severe evidence still cause bounded repair and failure if unrepaired.
`scoreProvisional=true` identifies evaluations requiring review; it does not change scoring.

`confidence` is nullable for compatibility. New prompts request null; legacy values are
uncalibrated model reports and must not be displayed as measured probabilities.

For the original consultation definition, model output first inventories substantive
`requests`: client message ID, concise request, operator answer IDs and resolution
(`answered`, `partial`, `next_step`, `unanswered`). IDs and actor roles are validated;
resolution remains a model assessment. A maximum score alongside an unresolved request
is flagged for review without silently changing the criterion answer. Replaced criteria
do not inherit this original-consultation requirement. Extraction can still mistake
acknowledgments for requests or omit a follow-up; this is not independently verified coverage.

Malformed structure receives a bounded full repair; parsed grounding errors receive
fresh focused prompts containing only the affected criteria and the original transcript,
merged with already validated findings. Each draft/Critic phase has
at most three generation attempts. An invalid final result is never persisted. The
Critic remains mandatory and receives its own budget after a valid draft.
Repair feedback distinguishes a quote/source mismatch from a missing checked-range ID.
When a quote occurs elsewhere verbatim, it lists candidate source IDs for the model to
inspect; it never moves a citation or changes an answer automatically.

## Normalized text and source preservation

`normalization.py` repairs only reversible Latin-1/CP1252 misdecoding that improves
Cyrillic text without replacement characters. Ambiguous Latin-only corruption is left
unchanged. Correct RU/KZ/EN text, IDs and timestamps are preserved.

The CLI importer preserves `originalRecord` when repairs occur. Foundation imports
retain `original_payload` and store normalized message text. Browser input is normalized
inside `Evaluator.evaluate`, before hashing, prompting and validation. When changed, the
response includes normalized `messages` in the existing message shape and a `normalization`
record containing original changed spans. Existing `App.applyEvaluation` spreads those
messages into the dialogue, synchronizing display without frontend edits. Before a
successful evaluation, the browser importer can still display its original corrupted text.

Original private dataset files are never rewritten. History may contain private text;
keep databases and benchmark outputs private.

## Metadata, cache, and Critic measurements

The existing cache includes normalized request, checklist, configured model/endpoint,
generation settings, prompt and Critic instructions, actual output schema, versioned
pipeline and normalization configuration. Definition and weight edits invalidate it.
There is no second cache. Cache keys use model tags; replacing model weights under the
same tag requires `force=true` or clearing that model's cache through an explicit policy.

Results retain old fields and add `requestedModel`, `checklistFingerprint`,
`promptVersion`, `schemaVersion`, `pipelineVersion`, `generationSettings`, `usage`,
`durationSeconds`, `draftResults`, `criticChanges`, `reviewRecommended`, and
`evidenceValidation`. The returned model name comes from Ollama when available.
`usage` distinguishes draft/Critic, targeted repairs, token counts and duration.
`criticChanges` records answer/evidence changes; these are not automatically improvements.
One additional independent `risk_review` is enabled when the matched identification
criterion is NO and the matched severe criterion is NO. It evaluates actual qualifying
acts independently; C3 failure is never automatically a C8 violation. `riskReview`
records the outcome separately from Critic changes. A failed optional review retains
the last fully validated result and requires human review; invalid replacement findings
are not persisted. Set `CQA_VERIFY_SENSITIVE=false` to disable this additional check.
Temperature zero and a seed do not guarantee identical fresh inference. A cache hit is
not a reproducibility experiment.

Optional request `context` can carry authorized knowledge or `incomplete=true`;
`audioObservations` can carry supplied measurements. Neither downloads audio. Only
text is assessed without observations. These are caller-supplied data, not instructions.

## Frontend owner handoff (no frontend source edits)

1. `frontend/src/data.js::scoreEvaluation` uses floating-point `Math.round`.
   `ReviewWorkspace.jsx` and appeal recalculation use it. Match Python Decimal half-up:

   | Unrounded percentage | Expected |
   | --- | --- |
   | 1.005 | 1.01 |
   | 50.625 | 50.63 |
   | all scored criteria N/A | null |

   Example input for the first two vectors: one scale criterion with weight 1,
   scale `[0, value, 100]`, and answer `value`. Also test fractional weights, N/A
   redistribution and a positive critical flag that leaves the percentage unchanged.
   A blanket `Number.EPSILON` adjustment does not establish general decimal parity.

2. `App.jsx::criterionSummary` hardcodes IDs `1,2,4,5,7` and original labels. Derive
   labels and aggregates from the selected checklist/snapshot; distinguish versions
   and avoid combining replaced criteria solely because their IDs match.

3. `saveCriterion` increments the version, but the batch panel selects only pending
   dialogues. Add stale-result indication and a batch action for reevaluating completed
   conversations under the active checklist. Preserve old snapshots/history. Individual
   reevaluation and CLI `evaluate --id ID --force` already use the current rubric.

4. Optionally display review metadata, multiple quotes and checked-range absence evidence.
   Show a provisional/review badge for `scoreProvisional`/`reviewRecommended`, so an
   unresolved interpretation is visible. Keep current fields as the compatibility fallback.
   Server score is authoritative.

## PowerShell validation

Run from the AI worktree. The isolated environment is outside the repository:

```powershell
$cqaPython = 'C:\Users\Insar\cqa-ai-venv\Scripts\python.exe'
& $cqaPython -m pytest -q
& 'C:\Users\Insar\cqa-ai-venv\Scripts\ruff.exe' check src tests examples
& 'C:\Users\Insar\cqa-ai-venv\Scripts\ruff.exe' format --check src tests examples
& $cqaPython -c "from cqa.workspace import default_checklist; print(len(default_checklist()))"

$env:CQA_MODEL = 'qwen3:4b-instruct'
$env:OLLAMA_URL = 'http://127.0.0.1:11434'
$env:CQA_NUM_CTX = '32768'
$env:CQA_NUM_PREDICT = '5000'
$env:CQA_SEED = '42'
$env:CQA_DB = 'C:\Users\Insar\cqa_hackathon\results\local-app.sqlite3'
& $cqaPython -m cqa serve --port 8767
```

Other settings: `CQA_NUM_PREDICT` (default 5000), `CQA_TIMEOUT` (600 seconds),
`CQA_CONCURRENCY` (1). `CQA_SEED=none` omits the seed. Production model/context defaults
are preserved. Context guards reject oversized prompts instead of silently truncating them.
Generation is bounded by a wall-clock deadline as well as HTTP timeouts and retry limits.

Private benchmark (choose a NEW output directory for every run):

```powershell
& $cqaPython -m cqa.private_benchmark `
  --dataset 'C:\Users\Insar\cqa_hackathon\data\dev.json' `
  --labels 'C:\Users\Insar\cqa_hackathon\benchmark\manual_labels.csv' `
  --baseline 'C:\Users\Insar\cqa_hackathon\benchmark\model_predictions.csv' `
  --output-dir 'C:\Users\Insar\cqa_hackathon\results\team-new-run' `
  --extra-ids p1-kz-001 p1-kz-011 p1-en-007 --include-synthetic
```

The adapter calls the active evaluator, explicitly maps `01..08` to `1..8`, and
accepts only loopback Ollama. It writes predictions before opening labels. It rejects
private input/output paths within a Git worktree. The private metrics report includes
agreement, coverage/MAE, disagreements, N/A, flags, mechanical evidence checks, latency,
pass counts and draft-to-final changes against provisional labels. It does not measure
semantic evidence accuracy without independent human review. No annotations enter prompts.

Explicit real API acceptance on the synthetic example, including changed criteria,
cache bypass and app-history recovery in a fresh Python process:

```powershell
$env:CQA_NUM_CTX = '16384'
$env:CQA_NUM_PREDICT = '2000'
& $cqaPython examples/cqa_live_smoke.py `
  --output-dir 'C:\Users\Insar\cqa_hackathon\results\live-new-run'
# For the Kazakh synthetic input, additionally pass:
# --conversation-id synthetic-live-next-action-kz
```

For the full private eight-criterion benchmark use context 32768 and output limit 5000.

## Demo acceptance

Unit tests alone do not establish full live-demo readiness. Verify separately: new
conversation → evidence review → severe filter → appeal/review → criterion replacement →
reevaluation → restart/history. Browser contract tests mock LLM output and must be labelled
accordingly. Real Ollama measurements and outstanding UI issues belong in the integration report.
