# Phase 3 baseline — 2026-11-07

Начальная ревизия: `58f249c`, чистый `main`, `git pull --ff-only origin main`
подтвердил актуальность. Изучены Phase 2 runbook, verification, handoff,
backend guide, провайдеры, очередь, CLI, Dockerfile и Compose.

Проверки из существующего `.venv`:

- `python -m pytest tests/cqa -q`: 100 passed, 1 skipped (22.10 s).
- `ruff check src tests examples`: passed.
- `ruff format --check src tests examples`: passed, 74 files.
- `npm --prefix frontend run build`: passed, Vite 6.4.5.
- `docker compose -f compose.foundation.yml config --quiet`: passed.
- Docker Engine: недоступен, pipe `dockerDesktopLinuxEngine` отсутствует.
- Ollama `/api/tags`: установлен `qwen3:4b`, Q4_K_M, 2,497,293,931 bytes.
- GPU: RTX 3060 Laptop, 6144 MiB; исходно модель выгружена, VRAM usage 0 MiB.

Число 148 из прошлого отчёта относится к более широкому набору проверок;
фактический текущий результат команды `tests/cqa` указан выше.
Системный Python не содержит pytest; команды следует запускать через `.venv`.

Первый установленный пробел: successful-result metadata не учитывала retries,
Ollama load duration и невалидные/прерванные вызовы. Добавлена отдельная
таблица `cqa_job_metrics`, создаётся `create_all` без изменения старых таблиц.
Тексты, URL и upstream error bodies в telemetry не сохраняются.
