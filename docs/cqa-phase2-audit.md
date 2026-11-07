# Phase 2: baseline audit (2026-11-07)

Baseline on synchronized `main`, before implementation:

- `.venv/Scripts/python.exe -m pytest tests/cqa -q`: **72 passed, 1 skipped**
  (private DEV path was not supplied), one Starlette/httpx deprecation warning.
- With `CQA_TEST_DEV_FILE` pointing at the private local DEV file:
  `pytest tests/cqa/test_foundation_data.py -q`: **9 passed**.
  File contents and signed URLs are not included in this report or Git.
- `ollama list` and local `/api/tags`: `qwen3:4b`, 4.0B, Q4_K_M available.
  NVIDIA tooling reports RTX 3060 Laptop GPU, 6144 MiB. No generation performed
  at this baseline stage; model availability alone does not prove inference.

## Existing paths

`cqa.api` calls `cqa.service.Evaluator`, stores legacy evaluations and workspace
in `CQA_DB`, and hosts the built frontend. The frontend sends inline messages,
criteria and version to `/api/evaluate`; appeals are edited inside workspace.

`cqa.backend.main` uses SQLAlchemy Foundation tables, append-only checklists,
durable jobs, atomic result commits and review snapshots. Its worker, cache,
importer and optional agent protocols have working automated tests. It does
not yet serve the frontend contract or its assets. Running both applications
creates independent evaluation histories.

ProviderEvaluator reuses the AI owner's RULES, Analysis schema, quote validation
and scoring engine. It has a real HTTP path but only one evaluation pass.
Provider adapters retry transient failures and bound concurrency; they currently
discard usage, hardcode output/context limits, and do not bound OpenAI input.
No separate team Evaluator/Critic is integrated. Basic extractor/classifier
are optional structural helpers, not semantic quality assessment.

## Implementation boundary

Foundation becomes the authoritative store and queue. Both ASGI names will point
to the same application implementation. A compatibility adapter will translate
legacy requests/results, workspace checklist edits and reviews into Foundation
records. No new scoring formula or independent evaluator is needed. Existing
legacy databases remain intact; migration must be explicit and reviewable.

React components remain owned by participant 3. Changes needed for provider
labels, version selection and asynchronous job presentation will be specified
in an API handoff. The stale graphify graph contains TokenOps symbols rather
than CQA; CQA audit findings above were verified directly against source/tests.
