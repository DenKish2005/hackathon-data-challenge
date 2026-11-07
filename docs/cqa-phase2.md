# Phase 2: единое приложение и запуск

## Что соединено

`cqa.api:app` — совместимое имя того же объекта `cqa.backend.main:app`.
Все HTTP-маршруты, CLI, jobs, оценки, версии и апелляции используют Foundation.
Собранный React обслуживается тем же HTTP-сервером. React-компоненты не изменены.
`cqa.service` остаётся владельцем RULES, Analysis, проверки цитат и scoring;
его старые Store/Evaluator сохранены для совместимости импортов, но приложение
и CLI их больше не запускают.

Путь оценки: сохранённый разговор + неизменяемая версия → job в SQLite → managed
worker → ProviderEvaluator → строгая схема и цитаты → необязательный ProviderCritic
с существующей командной инструкцией → повторная валидация → существующий scorer
→ атомарное сохранение результата и completed job → UI.
Отказ модели оставляет failed job без оценки; автоматического перехода в mock нет.

## Установка и Mock Mode (PowerShell)

Из корня репозитория, Python 3.11+ и Node 20.19+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
npm --prefix frontend ci
npm --prefix frontend run build
$env:DATABASE_URL = 'sqlite:///.runtime/cqa-foundation.db'
$env:LLM_PROVIDER = 'mock'
python -m cqa serve
```

Открыть [локальное приложение](http://127.0.0.1:8000), документацию — `/docs`.
Mock Mode не требует Ollama/GPU. Синтетические результаты имеют `is_mock:true` и
явные синтетические обоснования. Текущий UI имеет старые подписи про Ollama:
см. [точный handoff владельцу UI](cqa-phase2-handoff.md).

Для разработки отдельно `npm --prefix frontend run dev`; Vite проксирует `/api`
на порт 8000. Один Python-процесс на SQLite-файл; размер пула задаёт `CQA_WORKERS`.
`.env.example` — образец: Python сам не загружает `.env`; экспортируйте переменные.

## Настоящая локальная Ollama

Запустить установленную Ollama. Загрузка модели — отдельное ручное действие:

```powershell
ollama list
# Только если нужная модель ещё не установлена:
ollama pull qwen3:4b
$env:LLM_PROVIDER = 'ollama'
$env:LLM_BASE_URL = 'http://127.0.0.1:11434'
$env:LLM_MODEL = 'qwen3:4b'
$env:LLM_CONCURRENCY = '1'
$env:LLM_CONTEXT_SIZE = '16384'
$env:LLM_OUTPUT_LIMIT = '4096'
$env:LLM_TIMEOUT = '240'
$env:CQA_JOB_TIMEOUT = '500'
$env:CQA_ENABLE_CRITIC = 'false'
python -m cqa serve
```

Это проверенная конфигурация одного прохода полного официального чек-листа на
коротком синтетическом RU-диалоге. Два прохода включаются
`CQA_ENABLE_CRITIC=true` (по умолчанию true), требуют больше контекста и времени.
При большом тексте увеличьте контекст/лимиты с учётом памяти; текст никогда не
обрезается ради успешной оценки. Консервативная проверка считает UTF-8 байты,
schema, выходной резерв и overhead. Это верхняя оценка, не токенизатор модели.

На RTX 3060 Laptop 6 GiB полный чек-лист при контексте 16384 частично выполнялся
на CPU. Для быстрого двухпроходного smoke использовался отдельный сохранённый
чек-лист из одного критерия, контекст 10240, вывод 512; модель помещалась в GPU.
Измерения и пределы проверки — [фактический отчёт](cqa-phase2-verification.md).
Не выставляйте Ollama напрямую в публичную сеть.

## Альтернативный API

Только при разрешении организаторов на внешнюю обработку и осознанном выборе API:

```powershell
$env:LLM_PROVIDER = 'openai_compatible'
$env:LLM_BASE_URL = 'https://YOUR_APPROVED_HOST/v1'
$env:LLM_MODEL = 'YOUR_CONFIGURED_MODEL'
$env:LLM_API_KEY = 'YOUR_LOCAL_SECRET'
$env:CQA_ALLOW_EXTERNAL_DATA = 'true'
python -m cqa serve
```

Это конфигурационный пример, внешний запрос в ходе Phase 2 не выполнялся.
Адаптер использует `/chat/completions`, `response_format:json_object`; сервер
строго проверяет Analysis, ответы и доказательства. Провайдер должен поддерживать
такой контракт. Удалённая Ollama тоже требует разрешения; loopback и явный локальный
Docker alias `host.docker.internal` считаются локальными.

## Переменные

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///.runtime/cqa-foundation.db` | Единственная рабочая БД |
| `LLM_PROVIDER` | `mock` | mock / ollama / openai_compatible |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | пусто | Явный endpoint/model/секрет |
| `LLM_CONCURRENCY` | 1 | Общий лимит HTTP-вызовов модели |
| `LLM_TIMEOUT` | 60 | HTTP timeout, секунды |
| `LLM_ATTEMPTS` | 3 | 1–5 попыток при transport/429/5xx |
| `LLM_CONTEXT_SIZE` | 65536 | Безопасный предел контекста |
| `LLM_OUTPUT_LIMIT` | 8000 | Лимит токенов вывода |
| `CQA_WORKERS` | 2 | Размер managed worker pool |
| `CQA_JOB_TIMEOUT` | 120 | Общий предел выполнения job |
| `CQA_ENABLE_CRITIC` | true | Существующий второй проход |
| `CQA_FRONTEND_DIR` | `frontend/dist` | Путь к сборке, при необходимости абсолютный |
| `CQA_ALLOW_EXTERNAL_DATA` | false | Разрешение на внешнюю передачу |
| `FREEDOM_DEV_API_URL`, `FREEDOM_CONTROL_API_URL` | пусто | Полные подписанные URL, только сервер |

429/5xx и сетевые таймауты повторяются с ограниченным exponential backoff;
401/403 не повторяются. Структурные ошибки/невалидные цитаты не превращаются в
успех. `done_reason:length`, незавершённый ответ, некорректный JSON и превышение
контекста отклоняются. Usage и время привязаны к отдельным вызовам, поэтому
конкурентные запросы не смешивают метаданные. Неизвестный usage остаётся неизвестным.

## DEV, одна оценка и партия

```powershell
# Локальный приватный файл. Повторный импорт идемпотентен.
python -m cqa import 'C:\private\cqa_dev_utf8_fixed.json'
# Или загрузить JSON через существующий UI; autosave импортирует его в Foundation.

# Требует уже запущенного backend; CLI использует его очередь и модель.
python -m cqa evaluate --id CONVERSATION_ID --checklist-id official --version 1
python -m cqa evaluate --limit 5 --timeout 600
# Вся партия, без --limit:
python -m cqa evaluate --checklist-id official --version 1 --timeout 600
# Явное повторение failed job / новая оценка без кэша:
python -m cqa evaluate --id CONVERSATION_ID --retry-failed
python -m cqa evaluate --id CONVERSATION_ID --force
python -m cqa export '.runtime\report.json'
```

`python -m cqa.backend` и `cqa-backend` поддерживают те же команды.
Для другого порта добавьте `evaluate --api-url http://127.0.0.1:8012`.
CLI печатает ID/status/score, не транскрипты; export — приватный локальный артефакт.
Если истёк срок ожидания CLI, job продолжает жить в БД: сохраните выведенный ID.

Оригинальные timestamps/audio URL, роли, порядок и стабильные canonical message IDs
сохраняются импортёром. Проверены 65 реальных записей локального DEV, 1268 сообщений,
35 RU / 15 KZ / 15 EN, 60 чатов / 5 звонков и повторный импорт без дубликатов.
Реальные транскрипты в LLM в ходе проверки не отправлялись; live-запросы синтетические.

## API и перезапуск

Создание задания (асинхронно, 202):

```json
{"conversation_id":"synthetic-001","checklist_id":"official","checklist_version":1}
```

Отправить на `POST /api/evaluations`, затем опрашивать
`GET /api/evaluation-jobs/{job_id}` до completed/failed. Сохранённая оценка:
`GET /api/evaluations/{evaluation_id}`. `result_json` — неизменяемый оригинал;
`final_result_json` — результат с решениями апелляций. UI использует финальную
оценку, история `/api/history/{conversation_id}` показывает оригинальные запуски.

`force:true` создаёт новый job и сохраняет старую оценку. Обычный следующий запрос
использует свежий job той же конфигурации. Ключ включает полный разговор, metadata,
checklist/version, RULES/prompt version, provider/model/лимиты, optional stages и scorer.
Изменение критериев создаёт новую версию и новую оценку. Не редактируйте таблицы вручную.

Остановите сервер и запустите его с тем же `DATABASE_URL` и конфигурацией.
GET результата и UI восстановятся из SQLite. Running jobs восстанавливаются,
после трёх аварийных попыток становятся failed. Изменившаяся конфигурация отклоняет
старый pending job; создайте новый. Блокировка запрещает второй worker на той же БД.
Внешний вызов при аварии может повториться; сохранение результата однократное.

Workspace PUT сохраняет импорты, checklist version, reviews и revision одной
транзакцией; конфликт вкладок возвращает 409. Баллы/ответы браузера не становятся
источником истины: workspace GET строится из canonical результатов. Синтетические
демо и косметические поля остаются в presentation state.

## Старые файлы и развёртывание

Старый `CQA_DB=.runtime/cqa.sqlite3` не удаляется и автоматически не переносится.
В проверенном рабочем окружении он содержит 0 оценок и не содержит workspace.
Если у другого участника есть старые оценки, сначала сохраните резервную копию
и экспорт из прежней версии: исторические записи не следует объявлять новыми
LLM-оценками. Импорт исходного DEV в Foundation безопасен и не меняет старый файл.
Добавленные workspace-таблицы создаются при старте; расширение cache key до 100
символов совместимо с существующей файловой SQLite. Иные СУБД требуют миграции.

```powershell
docker compose -f compose.foundation.yml up --build -d
```

Dockerfile собирает frontend в Node stage и включает его в backend image.
Compose публикует только `127.0.0.1:8000`, хранит БД в volume; модель самостоятельно
не скачивает. Для Ollama хоста контейнер использует `host.docker.internal:11434`.
Проверена конфигурация Compose; сборка/запуск контейнера здесь не проверены:
Docker Desktop engine недоступен. Локальный запуск без Docker проверен.

Для публичного demo нужен один TLS entry point, постоянный SQLite volume и backups,
секреты на сервере, доступ к выбранной модели, сетевой контроль доступа к приватным
диалогам, лимиты запросов/очереди и разрешение на передачу данных. Не публикуйте
DEV, API keys, подписанные organizer URLs или открытый Ollama. Публичное размещение
не выполнялось и не заявляется. Дополнительные агенты/облачные варианты — P2.
