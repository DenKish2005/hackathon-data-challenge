# Phase 3: технический результат и проверка — 2026-11-07

## A. Technical Summary

Развита существующая Foundation, без второго scoring/batch engine и без изменений
семантических промптов или React-компонентов.

- Отдельная таблица attempt telemetry сохраняет успешные, failed и прерванные
  managed-worker попытки без transcript, LLM content, URL или API credentials.
  Существующие SQLite-таблицы не изменялись; новая создаётся при старте.
- Provider adapters измеряют retries, HTTP attempts, ожидание semaphore, usage,
  длительность и Ollama load/prompt/eval timings. Неизвестный usage остаётся null.
- CLI ограничивает число активных задач, фиксирует версию чек-листа партии,
  фильтрует dataset group, сохраняет JSON/CSV после каждого результата, повторяет
  только failed из отчёта и восстанавливается через существующий server cache.
- Полные подписанные URL произвольных групп задаются приватным JSON map.
  Endpoint allowlist и проверка фактической группы ответа сохранены.
- `doctor`, PowerShell demo launcher и Compose readiness упрощают локальный запуск.
  Readiness обнаруживает недоступную Ollama/модель и неожиданно завершённый worker.
  Семантически невалидный/оборванный ответ не становится сохранённой оценкой.

## B. Performance Benchmark

Реальные измерения и ограничения сравнения: [performance report](cqa-phase3-performance.md).
Инструмент: `examples/cqa_performance.py`; отдельный локальный сервер/SQLite на
каждый запуск, только синтетические данные и уже установленная Qwen3 4B.

## C. Deployment Guide

Полные инструкции: [локальный запуск, Docker, batch, контрольный набор и сеть](cqa-phase3-deployment.md).

```powershell
powershell -ExecutionPolicy Bypass -File examples/cqa_demo.ps1
# Последующие запуски:
powershell -ExecutionPolicy Bypass -File examples/cqa_demo.ps1 -SkipBuild
```

React и FastAPI реально проверены на одном локальном HTTP entry point.
Сам `cqa_demo.ps1 -SkipBuild -Port 8017` также выполнен с отдельной пустой SQLite:
preflight `ready:true`, `/api/ready` — 200 `ready`/`is_mock:false`, `/` — 200.
Затем сервер корректно остановлен Ctrl+C.
Docker Compose config проверен, но Docker Engine здесь недоступен: настоящий
container build/runtime не подтверждён. Публичный tunnel не открывался.

## D. Live Demonstration Verification

`node examples/cqa_browser_smoke.mjs` выполнен в установленном Chrome через
Playwright. Сетевые API не подменялись. Вход: отдельный синтетический RU-диалог,
официальный чек-лист из 8 критериев, Qwen3 4B, context 16384 / output 4096,
Critic выключен, один worker/LLM-запрос.

1. Кнопка «Оценить диалог» вызвала настоящий `/api/evaluate` → durable job →
   Ollama → строгую validation → scorer → SQLite. Получены 8 результатов,
   балл 65, `is_mock:false`, время 88.04 s.
2. Все 8 критериев отображены в UI. Проверен итоговый балл и нажата ссылка
   «Реплика #m1»: исходное сообщение подсвечено.
3. Backend process остановлен, запущен на той же БД; создан новый browser context
   без localStorage прошлого контекста. Результат и балл восстановлены с сервера.
4. Через UI изменён заголовок первого критерия. После autosave запущена новая
   реальная оценка v2: 8 результатов, 65 баллов, 90.79 s. Получен новый evaluation ID.
5. Оригинальный `result_json` первой оценки совпал до и после изменения чек-листа;
   обе оценки присутствуют в серверной истории. Browser page errors отсутствуют.

Артефакты: [машинный отчёт](phase3-artifacts/browser-verification.json),
[снимок результата v2](phase3-artifacts/browser-v2.png).
Сохранение после перезапуска реально подтверждено. Скорость и валидность этих
трёхрепличных диалогов не подтверждают accuracy на DEV/CONTROL.

## E. Recovery Tests

| Сценарий | Проверка и поведение |
| --- | --- |
| Падение/недоступность Ollama | MockTransport network failure; readiness 503, без утечки endpoint/error body. Transport retries ограничены; failed job без Evaluation. Служба Ollama физически не останавливалась. |
| Generation timeout | Автотест worker timeout, failed и сохранение предыдущих результатов. HTTP timeout/retries покрыты provider tests. |
| Invalid/truncated JSON | Provider tests и реальный benchmark; telemetry сохраняется, Evaluation отсутствует. |
| Неверная схема/доказательства | Worker/pipeline tests и реальный benchmark; строгая validation сохранена. |
| Завершение worker неожиданной ошибкой | `/api/ready` → 503 `worker_unavailable`, публичный ответ без exception text. Перезапустить backend после устранения причины. |
| Отмена worker | Реальная asyncio cancellation в тесте; job остаётся running, новый worker восстанавливает, ложного completed нет. |
| Аварийные повторные старты | Running восстанавливаются, после 3 попыток failed; сохранение Evaluation однократное. |
| Параллельные jobs / повторные клики | Foundation concurrency/cache tests; одинаковый request без force возвращает один job. |
| Смена чек-листа во время job | Новый barrier-тест: старая и новая оценки сохраняют v1/v2 независимо. |
| Ошибки контрольного импорта/API | Invalid format/group/HTTP failures и rollback покрыты существующими data tests. Нового реального URL ещё нет. |
| Прерывание CLI | KeyboardInterrupt test: report с job ID и interrupted, код 130; серверное задание не отменяется. |
| Нет GPU / недостаточно RAM/VRAM | GPU необязателен для diagnostics, Ollama может работать на CPU. Физическая CPU-only машина и принудительный OOM не проверялись; автоматического fallback в mock нет. |

Дополнительно выполнен настоящий HTTP/CLI batch на 65 синтетических разговорах
в **mock-режиме**, parallel=3: 65/65 за 6.671 s. После остановки и запуска backend
на той же БД повторная партия: 65/65 cached за 1.719 s, все evaluation IDs те же.
Это проверяет batch/persistence, не производительность LLM. Ни одна из этих
цифр не является прогнозом времени реального контрольного набора.
[Машинный отчёт партии](phase3-artifacts/batch-65-verification.json).

## F. Integration Handoff

[Точные задачи участникам №2 и №3](cqa-phase3-handoff.md): вывод фактического
passes/provider/mock, ошибочные demo/review подписи в UI, durable polling для
сетевого показа, использование metrics и независимая проверка accuracy.

## G. Remaining Risks

- UI на настоящем результате всё ещё содержит статичные demo/«два прохода» подписи;
  это зафиксировано скриншотом и передано владельцу React. Его файлы не менялись.
- Реальные DEV/CONTROL не отправлялись в модель и не публиковались; качество
  и пропускная способность на 65 настоящих разговорах не измерены.
- SQLite worker — один backend process на БД. Для нескольких хостов нужен другой
  механизм владения очередью; копирование активной WAL-БД требует backup API.
- После hard crash внешний inference может повториться, хотя сохранённая оценка
  уникальна. Telemetry не может восстановить usage незавершённого upstream вызова.
- Контекст проверяется консервативной оценкой UTF-8 bytes, это не точный tokenizer.
  Длинный разговор будет отклонён, а не молча обрезан. Необходимо измерить его
  потребность в контексте/памяти на реальном наборе после разрешения команды.
- Приложение не имеет авторизации; публичный доступ разрешён только к отдельной
  синтетической БД. Сетевой timeout старого inline API требует UI polling.
- Docker build/runtime, публичный deployment, CPU-only inference и реальный OOM
  не подтверждены. Команды проверки Docker описаны отдельно.

## H. Git Changes и проверки

Работа в `main`, исходно чистый `58f249c`, предварительный ff-only pull выполнен.
Каждый законченный блок отправлен обычным push без force. Изменены backend/infra,
инфраструктурные tests, examples, docs и `.env.example` / Compose; React и
семантические файлы участников №2/№3 не изменялись.

Обязательные проверки: `python -m pytest tests/cqa -q`, `ruff check src tests examples`,
`ruff format --check src tests examples`, `npm --prefix frontend run build`,
`docker compose -f compose.foundation.yml config --quiet`, `git diff --check`.
Используется Python из `.venv`; системный Python не содержит pytest.

Дополнительный полный `pytest tests -q` на промежуточной ревизии: 112 passed,
1 skipped, 41 setup errors — все из-за отсутствующего настоящего Redis на
127.0.0.1:6379, требуемого TokenOps tests. Эти ошибки не скрыты; общий suite
не объявляется зелёным. Единственное предупреждение CQA — существующая deprecation
Starlette TestClient/httpx. Итоговый повтор обязательного CQA suite:
**111 passed, 1 skipped (35.67 s)**; lint, format, React build и Compose config
успешны. Пропущен opt-in тест приватного DEV, который требует локального пути
к набору; настоящий DEV для Phase 3 не использовался.
