# Phase 3: integration handoff

## Участнику №2 — семантика

RULES, CRITIC_RULES, Analysis, validate_analysis, проверка evidence и score не
изменялись. ProviderEvaluator → optional ProviderCritic → scorer остаётся единым
путём. Critic делает один дополнительный проход, циклического повторения нет.

Новая инфраструктурная telemetry: `GET /api/evaluation-jobs/{id}` → `metrics[]`,
по одному объекту на попытку worker. Внутри `calls[]` находятся реальные usage,
duration, provider wait, HTTP attempts/retries и Ollama load/prompt/eval timings.
Ошибка модели/валидации сохраняет telemetry, но не Evaluation. Эта информация
дополняет прежние `result_json.metadata.calls`, не меняет контракт Findings.

Фактический browser smoke с настоящей Qwen3 обработал официальный чек-лист из
восьми критериев и повторил оценку после изменения заголовка критерия. Это
проверка интеграции. Различие баллов на очень коротком синтетическом диалоге
между отдельными запусками не является оценкой accuracy.
Решение о финальном включении Critic и выборе модели остаётся за владельцем
семантики после сравнения с ручной разметкой. Новые модели не скачивались.

## Участнику №3 — UI

React-код не изменён. Добавлен воспроизводимый Playwright smoke
`examples/cqa_browser_smoke.mjs`; он запускает изолированный backend с локальной
Ollama, отдельной БД и синтетическим разговором. Проверяет кнопку оценки,
8 findings, балл, переход к evidence, процессный restart, свежий browser context,
редактирование критерия в UI и неизменность первой сохранённой оценки.

```powershell
node examples/cqa_browser_smoke.mjs
```

Нужны построенный `frontend/dist`, `.venv`, установленная Qwen3 4B и Chrome
(на Windows выбран Playwright channel `chrome`). Для другого браузера задайте
`CHROMIUM_PATH`; для другого Python — `CQA_PYTHON`.
Прогон специально без mock и без перехвата API. Результат, synthetic DB,
screenshots и журналы находятся в `.runtime/browser-smoke/<run>/`.

Фактические замечания к текущему UI, подтверждённые screenshot:

1. `EvaluationPanel.jsx`: статичный текст «Два прохода» показывается даже при
   одном проходе. Выводить `passes` завершённой оценки; до запуска показывать
   конфигурацию backend, а не обещать два прохода.
2. `ReviewWorkspace.jsx` / demo badges: на настоящем `source:"ollama"` результате
   остаётся подпись «Демо-оценка · без запуска модели». Показывать её только при
   `is_mock:true` или локальных демонстрационных данных. Синтетический *входной
   разговор* может быть оценён настоящей моделью: это другой признак.
3. `ReviewWorkspace.jsx`: `originalResults` после загрузки workspace присутствует
   и без пересмотра; подпись «После пересмотра» должна зависеть от
   `reviewRevision > 0`, а не только наличия originalResults.
4. Для сетевого показа заменить длинный `/api/evaluate` на `POST /api/evaluations`
   → poll `GET /api/evaluation-jobs/{id}` → `GET /api/evaluations/{id}`. Пока это
   не сделано, демонстрация длинной оценки через внешний proxy может оборваться.
   Возобновлять polling по job ID; не запускать force из-за сетевого timeout.
5. Ошибки `model_unavailable` из `/api/ready` и `metrics[].error_code` показывать
   понятным текстом: transport_error, context_limit, invalid_output,
   validation_error, job_timeout. Не показывать upstream error bodies.

Версии, scoring и сохранение уже работают через текущие endpoints. Полный
список контрактов и рекомендуемых миграций — `cqa-phase2-handoff.md`.

## Организаторский контрольный набор

Новый ID и отдельный подписанный URL задаются через `FREEDOM_DATASET_URLS_FILE`:
приватный JSON map, без изменения query и подписи. Сервер проверяет фактическую
группу ответа, формат, стабильные IDs и конфликт источников. Команда
`python -m cqa import --organizer EXACT_GROUP_ID` импортирует без браузера;
`evaluate --group-id EXACT_GROUP_ID --report ...` оценивает текущий выбранный
чек-лист. Настоящий новый URL организаторы ещё не предоставили; его live-import
не заявляется. Ошибки импорта, подпись/redaction и идемпотентность покрыты тестами.
