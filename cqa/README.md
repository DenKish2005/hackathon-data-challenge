# Freedom Broker CQA — isolated backend foundation

The `cqa/` directory does not change the pre-existing TokenOps Guard library or `frontend/` demo. The backend is an independent FastAPI server. Default evaluation runs use **synthetic mock output**, never a real quality verdict.

## Setup

From the repository root (Python 3.11+):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r cqa/requirements.txt
cp cqa/.env.example .env  # Windows: copy cqa\.env.example .env
python -m uvicorn cqa.backend.main:app --reload
```

Open http://127.0.0.1:8000/docs and http://127.0.0.1:8000/api/health.
Put the non-public DEV JSON into `cqa/data/cqa_dev_utf8_fixed.json` (or at the path specified by `CQA_DATASET_PATH`), or supply it directly using `source=payload`. Never commit the dataset to the public repository.

```bash
curl -X POST http://127.0.0.1:8000/api/datasets/import \
  -H 'Content-Type: application/json' -d '{"source":"local","group_id":"DEV"}'
```

The alternative `source=api` uses *only* `FREEDOM_DEV_API_URL` or `FREEDOM_CONTROL_API_URL` from the server's environment; callers cannot set an arbitrary URL. Control import requires a **new complete signed URL**, never hand-edit the DEV signature.

## REST integration (frontend owner)

- `GET /api/conversations?group_id=DEV&limit=100&offset=0` returns `{items,total,limit,offset}`; each item exposes `conversation_id, dataset_group_id, channel, language, audio_url, imported_at`.
- `GET /api/conversations/{conversation_id}?group_id=DEV` additionally returns `messages[]` with `message_id, message_index, speaker, timestamp_original, text` and `original_payload`. The frontend currently uses `id/role/time`: map from backend's corresponding fields and convert `agent chat`/`voice call` to `chat`/`call` for its presentation model.
- `GET /api/checklists`, `GET /api/checklists/{id}`, `GET /api/checklists/{id}/versions/{version}`; `POST /api/checklists` with `{checklist_id,criteria,sections,expected_version}` creates a new immutable version. First version must omit `expected_version`.
- `POST /api/evaluations` with `{conversation_id,group_id,checklist_id,checklist_version,force?}` returns `202` and a persistent `job_id`. Poll `GET /api/evaluation-jobs/{id}` until `completed` / `failed`, then fetch `GET /api/evaluations/{evaluation_id}`. Mock evaluations have `is_mock=true`, `result_json.is_evaluated=false` and `total_score=null`.
- `POST /api/appeals` with `{evaluation_id,criterion_id,comment}`; `GET /api/appeals/{id}`; `POST /api/appeals/{id}/review` with `{decision:'upheld'|'rejected',reason,revised_answer?}`. `upheld` requires `revised_answer`; rejected forbids it. Historical evaluation is never mutated. Appeal responses include immutable review history and revised answer without inventing a recalculated score.

## AI evaluation integration (AI owner)

Replace or inject `PipelineWorker.evaluator`: it must implement

```python
async def evaluate_conversation(conversation: dict, checklist: dict) -> dict: ...
```

`conversation` contains all original roles, timestamps, language, channel, message IDs; `checklist` is the immutable ID+version+criteria+sections. Return criterion IDs, answers, reasons, evidence_message_ids, checked_message_ids for absence, na_reason for N/A and metadata. Adapter for teammate's scoring engine should be injected as `scorer` (with async `.score(result, checklist)`), not implemented in the frontend or LLM. The built-in mock does not calculate quality scores. `BasicExtractor` and `BasicClassifier` are opt-in interfaces, not required steps.

`cqa.infra.llm` includes a mock, OpenAI-compatible provider, and Ollama adapter with concurrency and bounded retry. **Provider selection does not enable real evaluation until a real evaluator is injected.** `CQA_ALLOW_EXTERNAL_LLM=true` is needed for any remote external model. Do not send real call transcripts to third-party model APIs without permission. `cache_key` keys by transcript contents, checklist ID/version, prompt version and model.

## Checks and limitations

Run `python -m pytest cqa/tests -q`. Root TokenOps Guard tests may require an external Redis server; they are not modified. The worker polls durable SQLite jobs and recovers interrupted `running` tasks on startup. It is designed for **one web-worker process**, not multiple processes/containers; for deployment with multiple workers use an atomic claim/lease/lock and migrations, auth, secrets management, role permissions, secure CORS and protected storage of personal data. Since the official DEV dataset is not included, fixture tests validate the contract; the optional actual DEV integration test is skipped if the file is absent. API clients should not treat demo data as evidence of real operator performance.
