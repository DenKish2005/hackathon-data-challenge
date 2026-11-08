# Local Windows demo

React, FastAPI, SQLite and Ollama run on this laptop. Keep the unfinished frontend
stash untouched. No remote model API, new model download or benchmark is needed.

## Exact launch commands for the verified laptop

```powershell
Set-Location C:\Users\Insar\hackathon-data-challenge
$env:PYTHONPATH = "$PWD\src"
$env:LLM_PROVIDER = 'ollama'
$env:LLM_BASE_URL = 'http://127.0.0.1:11434'
$env:LLM_MODEL = 'qwen3:4b-instruct'
$env:CQA_STRATEGY = 'two_pass'
$env:CQA_ENABLE_CRITIC = 'true'
$env:CQA_WORKERS = '1'
$env:LLM_CONCURRENCY = '1'
$env:LLM_ATTEMPTS = '1'
$env:LLM_CONTEXT_SIZE = '32768'
$env:LLM_OUTPUT_LIMIT = '4096'
$env:LLM_TIMEOUT = '300'
$env:CQA_JOB_TIMEOUT = '600'
$env:DATABASE_URL = 'sqlite:///.runtime/local-demo.db'
Invoke-RestMethod http://127.0.0.1:11434/api/tags
npm --prefix frontend ci
npm --prefix frontend run build
& C:\Users\Insar\cqa-ai-venv\Scripts\python.exe -m uvicorn cqa.api:app --host 127.0.0.1 --port 8784
```

Open **http://127.0.0.1:8784**; leave the terminal running. Stop with Ctrl+C.
Port 8000 is already occupied by local Docker/WSL forwarding; those services are left untouched.
If Ollama is offline, start the installed application or run `ollama serve` in another
terminal. The installed tag is `qwen3:4b-instruct`. Do not start two workers on one DB.

These limits suit a short synthetic conversation and the standard checklist. Large
inputs may exceed the conservative context guard. The shared `.env.cqa.example`
retains 65536 for larger inputs; performance at that size was not tested here and it
can increase CPU offloading on an 8 GB GPU. A rejected input must remain an error.
Keep Critic and strict evidence validation enabled.
`LLM_ATTEMPTS=1` limits HTTP attempts, not semantic repairs: Draft and Critic can
each request additional validated generations. Allow several minutes for a live run.

For rehearsal without inference, change `LLM_PROVIDER` to `mock` and use another
SQLite path. Mock results are labelled and do not demonstrate model accuracy.

The supported launcher can reuse the installed environment:

```powershell
& C:\Users\Insar\cqa-ai-venv\Scripts\python.exe scripts/run-cqa.py --python C:\Users\Insar\cqa-ai-venv\Scripts\python.exe --check --port 8784
```

`--check` performs no inference. Omit it to launch; add `--skip-build` only after a
successful build. Existing `.env.cqa` settings take precedence over shell values;
use `--env-file` to choose a different local config. `--python` avoids creating
another environment. Imports are pinned to this checkout.

## Demonstration sequence

1. Check `/api/ready` and `/api/health`. Infrastructure readiness does not establish
   semantic accuracy. Initial synthetic examples are labelled demonstration data.
2. **Загрузить диалоги** → paste a small synthetic records/transcript JSON → import.
   The imported conversation is pending and has no invented score.
3. Select it → **Открыть аналитику** → **Оценивание и история запусков** →
   **Оценить диалог** once. Wait for the durable job. Avoid force/repeated submission.
4. Check each finding and N/A exclusion. Click **Реплика #…** to highlight the original
   message; inspect checked ranges for absent actions. N/A is not zero. An all-N/A
   assessment has no numeric score.
5. Provisional results must say **Предварительная оценка** and appear in **На проверке**.
   Exact quotes alone do not prove the criterion judgment is correct.
6. Appeal a criterion → **Апелляции** → review/save → reload. Original evaluations and
   history remain available. Rehearse with mock to avoid extra model calls.
7. Edit a rule. Existing results keep their snapshot; a new mock evaluation uses the
   new version. Check history, filters and **Общая статистика**. The breakdown follows
   dynamic criteria and shows **Нет данных** for missing applicable observations.

Audio import/playback and recovery use synthetic browser/API tests. Organizer access,
private recordings, remote hosting and long dialogues were not live-tested. Keep
signed URLs, transcripts, DBs and browser artifacts out of Git.

## Reproduce automated checks

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:CQA_TEST_PYTHON = 'C:\Users\Insar\cqa-ai-venv\Scripts\python.exe'
& $env:CQA_TEST_PYTHON -m pytest -q
& $env:CQA_TEST_PYTHON -m ruff check src tests examples scripts/run-cqa.py
& $env:CQA_TEST_PYTHON -m ruff format --check src tests examples scripts/run-cqa.py
node frontend/tests/scoring.mjs
node --test tests/vercel_proxy.test.cjs
npm --prefix frontend run build
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

In another PowerShell terminal, from the repository root:

```powershell
$env:BASE_URL = 'http://127.0.0.1:4173'
$env:CHROMIUM_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:CQA_TEST_PYTHON = 'C:\Users\Insar\cqa-ai-venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src"
node frontend/tests/smoke.mjs
node frontend/tests/evaluation.mjs
node frontend/tests/reliability.mjs
node frontend/tests/hardening.mjs
node frontend/tests/backend-flow.mjs
```

Browser integration uses its own temporary SQLite and explicit mock provider.
The scoring test compares against Python Decimal and never calls a model.
