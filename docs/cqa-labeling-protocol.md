# Next 6–10 manual labels

Keep the existing four labels unchanged. Select 6–10 additional complete dialogues
from the authorized local dataset: 2–4 RU, 2–3 KZ and 2–3 EN, including channels used
in the demo. Do not cherry-pick after seeing predictions. Save selection IDs and a
fixed holdout split before evaluating another model or prompt.

Include sufficient initial context versus necessary clarification; bot-collected
details; general navigation versus protected account acts; confirmed versus absent
verification; multiple substantive questions with partial/unanswered follow-ups;
an adequate next step; a real interruption versus an incomplete closing; explicit
waiting versus excluded first-response timing; and ambiguous/incomplete context.
Include a qualifying critical act only when present in authorized data; do not
manufacture one for the benchmark. These categories may overlap within one dialogue.

Two human reviewers label independently, blind to model outputs and to each other.
Freeze normalized transcript/hash, original roles/timestamps, complete dynamic
checklist/definition hash and version. For every active criterion record:

1. Applicability: applicable, not_applicable or uncertain, with a reason addressing
   the exact N/A condition. Missing behavior alone is not an N/A condition.
2. An allowed criterion answer; N/A only when permitted and applicable. Preserve
   uncertainty and disagreements rather than forcing an invented expert answer.
3. Exact evidence message IDs/quotes and roles, or the inspected range for absence.
   Identification needs the protected act and any preceding verification. Consultation
   needs all substantive requests and their actual resolution/next-step evidence.
4. A concise explanation and the rule text used. Do not import rules excluded by the
   active checklist, such as first-response thresholds in the shipped criterion 6.

Adjudicate disagreements with an experienced rubric owner while retaining both
original labels, disagreement category and final reason. If no defensible decision
is possible, mark it unresolved and report it separately from the exact-accuracy
denominator. Never use model outputs as replacement expert labels.

Calculate expected scores with the existing Decimal scorer after the criterion
labels are frozen. Keep labels in a separate private file; the inference command
must not read them. Freeze predictions before running comparison.

Report criterion-level exact matches as counts and percentages grouped by definition
hash; N/A TP/FP/FN/TN plus missing predictions; score MAE on completed paired cases;
completion/failure counts; and repeat agreement/score range only when fresh repeats
actually exist. Do not count a cached/replayed response as a consistency experiment.
Report an unanswered or failed run separately, not as a correct N/A or a zero score.

With 6–10 additional dialogues each criterion still has very few observations.
Publish sample counts, adjudication disagreements, language/channel coverage and
confidence intervals where meaningful. Separate developmental examples from the
holdout set; do not claim general or production accuracy from this sample.
