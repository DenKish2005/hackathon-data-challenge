# Phase 2: фактический отчёт — 2026-11-07

## A. Implementation Summary

- Два ASGI entry point объединены: `cqa.api:app` экспортирует Foundation app.
  Старые frontend endpoints адаптированы к общей очереди/БД, без нового scorer.
- Workspace импортирует источники, сохраняет версии критериев и проводит апелляции
  через Foundation в одной транзакции. GET проецирует authoritative findings/score;
  браузерный балл не становится сохранённой оценкой. Original result неизменяем.
- Все CLI имена используют Foundation; batch evaluator работает через HTTP jobs.
- Provider adapters настраивают concurrency, HTTP timeout, retries, context/output;
  отвергают невалидный JSON, обрезанный вывод и oversized context. Сохраняются
  фактические usage, время, model/provider, prompt version и валидированный Analysis.
- ProviderEvaluator, scoring и инструкция Critic переиспользуют существующий код
  команды. Critic включён по умолчанию, отключается явно для ограниченной памяти.
- Dockerfile включает сборку frontend; Compose передаёт настройки и сохраняет БД
  в volume. Добавлен явно запускаемый синтетический live-smoke example.

## B. Integration Status

| Переход | Что проверено |
| --- | --- |
| Frontend → совместимый API | Существующий browser smoke и интеграционные HTTP-контракты |
| Источник + версия → job | Общий job для `/evaluate` и `/evaluations`, включая параллельные запросы |
| Queue → HTTP model | Настоящая локальная Ollama через managed worker и ASGI API |
| Model → schema/evidence → score | Реальные валидные Analysis, точные цитаты и общий scorer |
| Score → SQLite → restart | Сохранённые live evaluations открылись после нового lifespan |
| Checklist edit → reevaluation | Новый job, сохранение старой версии, включая version-only изменение |
| Appeal → final score | UI adapter и REST; immutable original; несколько последовательных review snapshots |
| Provider switching | Ollama/OpenAI-compatible через MockTransport; внешний live API не вызывался |

React-компоненты не изменены. Подписи provider/mock, выбор исторической версии и
новый polling UI — конкретный [handoff участнику №3](cqa-phase2-handoff.md).
Отдельные командные Evaluator/Critic участника №2 пока не подключены; временный
реальный путь ProviderEvaluator работает. Контракт их подключения сохранён.

## C. Verification

До изменений: **72 passed, 1 skipped**, 14.08 s в `tests/cqa`.
Пропуск — приватный DEV без указания пути. С указанием локального файла исходный
набор data tests: **9 passed**. После реализации:

```powershell
$env:CQA_TEST_DEV_FILE = 'C:\private\cqa_dev_utf8_fixed.json'
$env:TEST_REDIS_URL = 'redis://127.0.0.1:6380/15'
.venv\Scripts\python.exe -m pytest -q
```

**148 passed, 1 warning, 35.56 s**, без пропусков. Redis — локальный отдельный
тестовый процесс, loopback:6380; тесты работают в собственных namespaces.
Предупреждение: Starlette deprecation для httpx TestClient; тесты проходят.
Платных запросов в автоматических тестах нет.

Дополнительно прошли:

- `ruff check src tests examples` и `ruff format --check src tests examples`.
- `npm --prefix frontend run build`: Vite build, 6.48 s.
- `npm run test:smoke` с Chrome и `BASE_URL=http://127.0.0.1:8012`:
  scoring, sorting, queue filters, reports, linked evidence, appeals/recalculation,
  checklist editor, import, keyboard modal и mobile review. Это существующий UI
  smoke с подменой части API, а не browser-to-live-model quality benchmark.
- Отдельный настоящий TCP backend: `/` → 200 и `/api/health` → mock metadata;
  batch CLI создал и дождался job через HTTP, получил сохранённую оценку.
- `docker compose -f compose.foundation.yml config --quiet`.

Локальный настоящий DEV: **65 диалогов, 1268 сообщений**, 35 RU / 15 KZ / 15 EN,
60 чатов / 5 звонков. Проверены порядок/роли/тексты/исходные timestamps/audio_url
всех записей; повторный импорт пропускает 65 записей. DEV импортирован также в
локальную рабочую `.runtime/cqa-foundation.db`: imported=65, затем skipped=65.
Данные и БД исключены из Git. Реальные разговоры в LLM не отправлялись.

## D. Live LLM Status

Настоящая Ollama на `http://127.0.0.1:11434`, **qwen3:4b**, 4.0B, Q4_K_M,
локальный model ID `359d7dd4bcda`. GPU: **NVIDIA GeForce RTX 3060 Laptop, 6144 MiB**.
Никакой моделью mock при этих запросах evaluator не подменялся.

Все запросы использовали только синтетические диалоги. Проверялся весь API-путь
в ASGI TestClient с реальным provider HTTP, managed worker, validation, scoring и
SQLite; это не MockTransport. После нового app lifespan GET результатов совпал
с сохранёнными данными, `is_mock:false`. Browser click с настоящей моделью отдельно
не проверялся; граница UI проверена контрактами и существующим browser smoke.

| Сценарий | Время API | Input tokens | Output tokens | Всего | Проходы |
| --- | ---: | ---: | ---: | ---: | ---: |
| RU, сохранённый smoke-чек-лист, 1 критерий | 18.294 s | 3426 | 924 | 4350 | 2 |
| KZ, тот же чек-лист | 12.481 s | 3536 | 894 | 4430 | 2 |
| EN, тот же чек-лист | 8.395 s | 3193 | 572 | 3765 | 2 |
| RU, **полный официальный чек-лист, 8 критериев** | **114.893 s** | **2306** | **2553** | **4859** | **1** |

Smoke: context=10240, output=512, evaluator + Critic; `ollama ps` показал 100% GPU,
около 4.2 GB. Полный чек-лист: context=16384, output=4096, Critic явно отключён;
около 5.4 GB, 21% CPU / 79% GPU. Получился валидный итог 65/100 на синтетическом
RU-примере; это фактический результат модели, **не свидетельство accuracy**.

Новый `examples/cqa_live_smoke.py` также выполнен через ASGI TestClient с настоящей
Ollama: ещё три синтетических RU/KZ/EN запроса, два прохода, HTTP/API jobs completed,
время 12.922 / 11.890 / 7.922 s, `is_mock:false`. Скрипт отказывается выполнять
live-проверку на mock или OpenAI-compatible provider. Для обычного запуска он
обращается к уже запущенному серверу, не создаёт фоновую службу.

Начальные пробы context=32768/20480 вызвали существенный CPU offload; они были
остановлены при настройке памяти. Их незавершённые jobs отклонены при восстановлении
с новой конфигурацией, без фиктивных evaluations. Полный официальный чек-лист с
Critic на этой машине в этих прогонах не подтверждён. Два прохода подтверждены
отдельно на smoke-чек-листе, полный чек-лист — на одном проходе.

Метаданные каждого вызова и результаты сохранены локально в исключённых из Git
`.runtime/phase2-live.db` и `.runtime/phase2-full-live.db`. В Git — только этот
отчёт с агрегатами, без клиентских данных. Внешние API и платная инфраструктура
не запускались; дополнительные модели не скачивались.

## E. Deployment Instructions

[Команды установки, запуска, env, DEV, партии и перезапуска](cqa-phase2.md).
Базовый запуск: `python -m cqa serve`; один Python-процесс, один DATABASE_URL,
один выбранный provider. `CQA_FRONTEND_DIR` указывает на сборку frontend.

Локальный запуск проверен. Публичного URL/развёртывания нет. Docker Engine здесь
недоступен, поэтому image build и container runtime не заявляются проверенными.
Автоматическая проверка среды отклонила запуск дополнительного фонового LLM-сервера
с причиной `blocked by policy`; генерация проверялась в ограниченных тестовых
процессах. Это не означает отказа самой Ollama или подмены live-проверки mock.

## F. Remaining Work

1. Участник №2: подключить командные semantic Evaluator/Critic, провести независимую
   разметку/accuracy benchmark. Проверка существования цитаты не доказывает вывод.
2. Участник №3: выполнить точные UI-изменения из handoff (provider/mock labels,
   historical version picker, jobs polling, явный rejected review workflow).
3. На целевом оборудовании проверить full-checklist + Critic и длинные RU/KZ/EN
   звонки с допустимыми latency/context; отдельный реальный browser click до LLM.
4. На целевом хосте проверить Docker image/run, TLS entry point, постоянный volume,
   backups/restore, доступ к модели, секреты и разрешения на обработку данных.
5. Импорт старой legacy-БД при наличии исторических записей — отдельная явная
   миграция с резервной копией; рабочий проверенный legacy-файл содержал 0 оценок.

Эти ограничения не скрываются за успешными тестами транспорта или availability.
