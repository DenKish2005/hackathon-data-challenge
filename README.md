# Freedom CQA — оценка качества диалогов

[Архитектура и зоны ответственности агентов](docs/CQA_ARCHITECTURE.md) · [Проверка интерфейса и ревью](frontend/design-qa.md)

Добавлен отдельный **Backend Foundation**: REST API, импорт, неизменяемые версии чек-листов,
очередь в БД, mock/provider adapters и история апелляций. Запуск без LLM:
`python -m cqa.backend serve`, затем `/docs`.
Локальный импорт: `python -m cqa.backend import PATH_TO_JSON`.
[Команды, API-контракт, интеграция AI и ограничения](docs/cqa-backend.md).
Существующий frontend/workspace и его запуск ниже сохранены; переход на новые endpoints
выполняется отдельной интеграцией.

Рабочее место аудитора: импорт RU/KZ/EN, оценка новых транскриптов локальной LLM,
настраиваемый чек-лист, цитаты, апелляции, пересмотр, история и экспорт.
Первый запуск содержит явно помеченные синтетические примеры; импортированные диалоги
остаются без оценки до успешного ответа модели. Сервис никогда не заменяет отказ LLM
фиктивным баллом.

## Запуск одной командой (Windows / macOS / Linux)

После распаковки или клонирования проекта откройте терминал в корне:

```powershell
python scripts/run-cqa.py
```

Требуются Python 3.11+ и Node.js LTS. Скрипт подготовит виртуальное окружение, соберёт интерфейс и запустит один адрес `http://127.0.0.1:8000`: и сайт, и API. Оставьте терминал работающим. Так не возникает рассинхронизации между старым Vite-процессом и API. `--check` проверяет настройки без установки и запуска, `--skip-build` использует уже готовую сборку.

Чтобы приватно сохранить выданный URL организаторов для сервера:

```powershell
python scripts/run-cqa.py --configure-source
```

Вставьте ссылку в скрытое поле терминала. Она сохранится в `.env.cqa`, который исключён из Git. Шаблон остальных параметров — `.env.cqa.example`. Не помещайте ссылку во frontend, коммиты или настройки публичной сборки.

Для настоящей оценки нужен запущенный Ollama с выбранной моделью либо доступный `OLLAMA_URL`. Пока модель недоступна, импортированные чаты и звонки остаются без оценки. Телефонный разговор анализируется по исходной расшифровке; его настоящая аудиозапись показывается при наличии `audio_url`. Аудио без транскрипта не получает вымышленный текст или баллы.

Публикация: [Vercel и подключение постоянного backend](docs/VERCEL_DEPLOY.md). Доступ к аккаунту и backend настраиваются отдельно; запуск тестов не означает публичный деплой.

## Запуск вручную

Требуются Python 3.11+ (проверен 3.12), Node 20.19+ (проверен 24), Docker Compose.
Команды из корня репозитория:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
docker compose -f compose.cqa.yml up -d
# Пример модели; можно заменить на более крупную при наличии RAM/GPU.
docker compose -f compose.cqa.yml exec ollama ollama pull qwen3:4b
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn cqa.api:app --host 127.0.0.1 --port 8000
```

Откройте порт 8000 в браузере. API и собранный frontend обслуживаются одним сервером.
Для разработки: оставьте API запущенным, в другом терминале `cd frontend && npm run dev`.
Vite передаёт `/api` серверу на 8000.
Для доступа с другой машины задайте bind-адрес осознанно: сервис рассчитан на локальную
демонстрацию без авторизации, как разрешено заданием, и содержит диалоги.

Ollama по умолчанию работает на CPU; первый запуск скачивает около нескольких ГБ.
Более крупные модели могут повысить качество, но требуют больше RAM и времени.
Модель не выбиралась по закрытым эталонам: её точность необходимо измерить.
Если Ollama уже установлена, Compose не нужен: `ollama serve`, затем `ollama pull qwen3:4b`.

Параметры сервера (экспортировать до запуска):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Адрес Ollama |
| `CQA_STRATEGY` | `two_pass` (launcher: `multi_agent`) | Специалисты + критик либо прежние два прохода |
| `CQA_AGENT_CONCURRENCY` | `1` | Лимит параллельных специалистов (1–8) |
| `CQA_MODEL` | `qwen3:4b` | Точное имя загруженной модели |
| `CQA_DB` | `.runtime/cqa.sqlite3` | SQLite, сохраняйте файл при переносе |
| `CQA_CONCURRENCY` | `1` | Ограничение параллелизма CPU |
| `CQA_NUM_CTX` | `65536` | Контекст с запасом для полного текста и проверки; требует RAM |
| `CQA_DATA_URL` | отсутствует | Подписанная ссылка организаторов, только сервер |

Не добавляйте подписанную ссылку в Git или frontend. Кнопка «Получить данные организаторов»
обращается к серверу и позволяет задать group_id. Альтернатива — загрузить предоставленный
JSON-файл через «Загрузить диалоги». Для оценки не требуется API организаторов, если файл уже есть.
В облачном окружении нужны разрешения для реестра Ollama, его CDN перенаправлений и API организаторов.
Compose сохраняет TLS-проверку и монтирует системный CA bundle для прокси окружения.

## Рабочий сценарий

1. Загрузите DEV или новый JSON `data.records` через интерфейс.
2. В «Критерии оценки» проверьте/измените правило, вес, шкалу, N/A. Сохранение создаёт версию.
3. Откройте диалог и нажмите «Оценить диалог» либо оцените очередь целиком.
4. Прочитайте обоснования и перейдите к репликам. У исходной оценки есть модель,
   версия чек-листа, проверенный участок, уверенность и точная цитата в JSON-экспорте.
5. Оспорьте критерий, затем в разделе апелляций сохраните решение и причину.
   Исходные оценки сохраняются, итог пересчитывается. Сервер хранит рабочее пространство
   (диалоги, чек-лист, апелляции) в SQLite; при недоступности сервера остаётся браузерная копия.
   Конфликт вкладок не перезаписывается молча — экспортируйте изменения и обновите страницу.
6. «История AI-оценок» показывает неизменяемые серверные результаты предыдущих запусков.

Сохранение рабочего пространства выполняется автоматически раз в 1,5 секунды. Дождитесь
сообщения о сохранении перед закрытием. Это одно общее демонстрационное пространство,
без разделения по пользователям. На статическом GitHub Pages работает только UI:
для настоящей оценки нужен запущенный Python API и Ollama.

## Многоагентный режим

`CQA_STRATEGY=multi_agent` включает отдельного специалиста на каждый текущий критерий и финального критика. Все роли получают полный исходный разговор; критик перепроверяет ответы и доказательства. Добавленный критерий автоматически получает специалиста. Это логические роли общей Ollama-модели, отдельные модели не обязательны.

Python проверяет ответы и точные цитаты, затем рассчитывает один итог по актуальным весам, шкалам и правилам N/A. При отказе специалиста или критика частичный результат не выдаётся за готовую оценку. `CQA_AGENT_CONCURRENCY` ограничивает число специалистов, `CQA_CONCURRENCY` — все одновременные обращения к модели. По умолчанию оба лимита1, чтобы не переполнить память; под GPU их увеличивают после измерения нагрузки.

Скрипт запуска выбирает многоагентный режим. Для совместимости прямой запуск сервиса без настройки использует прежний `two_pass`. В кэше эти стратегии разделены. Ответ содержит реальные `agentRuns`, число вызовов/токенов и версию промптов. Программные тесты не доказывают рост точности относительно Ground Truth: это проверяется отдельным benchmark.

## Как оценивается новый текст

Первый проход Ollama оценивает оператора по текущему чек-листу; второй проход Critic
перепроверяет оценки на том же исходном тексте. Это логические роли одной модели.
Реплики bot/system служат контекстом, инструкции внутри транскрипта не являются командами.
JSON Schema ограничивает структуру; сервер дополнительно проверяет полноту критериев,
разрешённые ступени, N/A, существование ID и точное совпадение цитаты.
Некорректный вывод отправляется на исправление, число попыток ограничено.
Проверка цитаты подтверждает её существование, но не гарантирует правильность интерпретации.

Python рассчитывает весовые баллы, исключает N/A из знаменателя, округляет до двух знаков.
Грубая ошибка отмечается отдельно. Кэш зависит от текста, языка, полного чек-листа, версии,
модели и промпта. «Пересчитать без кэша» принудительно вызывает модель.
Число токенов сохраняется; платных API-вызовов в этой архитектуре нет.

## Проверка точности и технические тесты

DEV содержит 65 диалогов без Ground Truth. Процент точности без отдельной разметки не заявляется.
Для независимого сравнения экспортируйте отчёт и подготовьте отдельный JSON эталонов:

```json
[{"conversation_id":"new-001","score":85,"results":[{"criterionId":"1","answer":"Да"}]}]
```

```bash
python -m cqa.benchmark predictions.json ground_truth.json
```

Отчёт: доля точных совпадений по критериям, разбивка по критериям, MAE итогового балла,
число сравнимых диалогов и пропущенные диалоги (их критерии считаются ошибками).
Не добавляйте контрольные эталоны в промпты, кэш или обучение.

```bash
docker compose up -d --wait redis
TEST_REDIS_URL=redis://127.0.0.1:6379/15 python -m pytest -q
ruff check src tests examples
ruff format --check src tests examples
# При запущенном Vite и Chromium:
cd frontend
npm run test:smoke
```

Тесты CQA проверяют расчёты, доказательства, изменение чек-листа, кэш, историю,
ошибки модели, SQLite и конфликт сохранения. В них используется MockTransport:
это проверка программного контура, а не измерение качества настоящей LLM.

Существующий TokenOps Guard сохранён как самостоятельная библиотека:

---

# TokenOps Guard

Рабочий Python-пакет контроля расходов ИИ-агентов: **один `run_id` — один бюджет** для asyncio-задач, подагентов и независимых процессов. Redis Lua атомарно резервирует деньги и токены до запроса и идемпотентно фиксирует фактическое использование после ответа.

Реализованы STEER на 80%, сокращение ответа, fallback-модель, общий HALT, step/call caps, очередь или отказ по параллелизму, защита от повторяющихся действий, heartbeat, сверка зависших резервов и авторизованное восстановление. Демо и тесты не вызывают платные API.

## Быстрый запуск: Docker Compose

Нужен запущенный Docker Engine / Docker Desktop.

```sh
docker compose up -d redis
docker compose run --build --rm demo
docker compose run --build --rm tests
```

`demo` и `tests` используют profiles и запускаются указанными явными командами. Redis слушает только loopback хоста и сохраняет данные в named volume. Для остановки: `docker compose down`. Не удаляйте volume активных запусков: там лежит общий ledger.

## Локальная установка

Python 3.11+, Redis (рекомендуется 7.4). Команды выполняются из корня репозитория.

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d redis
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:TEST_REDIS_URL = "redis://127.0.0.1:6379/15"
tokenops-demo --scenario all
python -m pytest -q
ruff check src tests examples
ruff format --check src tests examples
```

Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
docker compose up -d redis
export REDIS_URL=redis://127.0.0.1:6379/0
export TEST_REDIS_URL=redis://127.0.0.1:6379/15
tokenops-demo --scenario all
python -m pytest -q
```

Если Redis запущен другим способом, достаточно указать его URL. Тесты используют уникальные пространства ключей и удаляют только собственные ключи; FLUSHDB не применяется. Отсутствие Redis — явная ошибка тестов. `.env.example` служит образцом; пакет сам не загружает `.env`, переменные надо экспортировать в окружение.

## Демонстрация A–E

```sh
tokenops-demo --scenario A
tokenops-demo --scenario B
tokenops-demo --scenario C
tokenops-demo --scenario D
tokenops-demo --scenario E
```

| Сценарий | Что происходит | Ожидаемый результат |
| --- | --- | --- |
| A — Normal | ResearchAgent использует локальный RAG/tool, AnalysisAgent анализирует, SummaryAgent формирует ответ | Один run, 3 LLM-вызова, $0.60, COMPLETED |
| B — STEER | Четыре вызова расходуют $0.80 из $1 | Однократный STEER, следующие два вызова fake-economy, итог $0.84 |
| C — HALT | Бюджета не хватает даже для fallback с минимальным ответом | HALTED, провайдер не вызван ни разу |
| D — Infinite Loop | Повторяются одинаковые запросы и результаты | Предупреждение и progress_guard после четвёртого вызова |
| E — Concurrent | 5 независимых OS-процессов резервируют по $0.40 из общего $1 | Ровно 2 допуска, общий резерв $0.80; после ответа расход $0.80 |

Сценарий E демонстрирует непосредственно atomic reservation с фиксированной ценой. Остальные показывают полную обёртку, где вместо отказа может сначала уменьшаться ответ или выбираться fallback. Резервы E удерживаются до наблюдения инварианта координатором, затем допущенные процессы вызывают FakeProvider и списывают фактический расход.

Короткие точки входа также доступны в `examples/multi_agent_demo.py`, `runaway_demo.py`, `concurrent_demo.py`.

## Интеграция в существующих агентов

```python
import asyncio
from redis.asyncio import Redis
from tokenops_guard import GovernedLLMClient, RedisLedger, bind_run, load_settings
from tokenops_guard.providers import FakeProvider

async def main():
    settings = load_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True,
                           socket_connect_timeout=2, socket_timeout=5)
    ledger = RedisLedger(redis)
    client = GovernedLLMClient(ledger, settings, {"fake": FakeProvider()})
    handle = await ledger.create_run(settings)  # Только на доверенном сервере.
    # Сохраните handle.admin_token в защищённом операторском хранилище ДО dispatch.

    async def agent(name, prompt):
        with bind_run(handle.context.child(name)):
            return await client.complete(prompt, max_output_tokens=100)

    try:
        results = await asyncio.gather(
            agent("ResearchAgent", "Research a topic"),
            agent("AnalysisAgent", "Analyze a topic"),
        )
        with bind_run(handle.context.child("SummaryAgent")):
            summary = await client.complete("Summarize: " + " ".join(r.text for r in results))
        print(summary.text)
        await ledger.finish(handle.context.run_id)
    finally:
        await client.aclose()
        await redis.aclose()

asyncio.run(main())
```

Вызывайте все платные LLM-операции через `GovernedLLMClient.complete()`. Инструменты и локальный RAG могут вызывать `ledger.record_step(context)` и `ledger.record_progress(context, action, result)` для общих лимитов и защиты от циклов. Отпечатки action/result хешируются, текст в Redis не попадает. Платный embedding/tool требует собственного тарифицируемого адаптера и резервирования до отправки.

`context.child()` сохраняет run_id, бюджет, trace_id и время начала. `create_run(parent_run_id=...)` намеренно отклоняется: создание дочернего агента не должно создавать новый ledger. `parent_run_id` в модели контекста — опциональная трассировочная метаинформация; финансовый scope всегда задаёт run_id.

В отдельном доверенном процессе создайте собственное Redis-соединение и получите контекст через `await ledger.get_context(run_id, agent_id)`. Настройки должны совпадать с исходным запуском; fingerprint не даст рабочему процессу увеличить лимиты или поменять цены. Redis, его credentials и низкоуровневый ledger API — доверенная инфраструктура, не интерфейс для произвольного клиента.

## HTTP и очередь: проверенный run_id

Нельзя делать `bind_run()` на основании произвольного пользовательского `X-Run-ID`.

```python
from tokenops_guard.context import RunContextSigner, bind_run

signer = RunContextSigner(secret_from_secret_store)  # bytes, >=32 bytes
headers = signer.headers(handle.context.child("remote-agent"), principal="worker-42", ttl_s=300)
# Передайте headers через внутренний HTTP или как metadata сообщения очереди.

# На получателе worker_identity берётся из аутентифицированной identity, не из headers.
verified = await signer.from_headers(headers, principal=worker_identity, ledger=ledger)
with bind_run(verified):
    response = await client.complete("Process authorized work")
```

HMAC проверяет целостность, UUID, expiry и audience; бюджет и статус загружаются из Redis. Сервис, выдающий capability, должен сначала авторизовать пользователя на конкретный запуск. Это строительный блок для внутренней интеграции, а не готовый authentication server. `admin_token` никогда не передаётся агентам или клиентским приложениям.

## Конфигурация и тарифы

- `config/policies.yaml`: бюджет, caps, STEER-порог, QUEUE/REJECT, таймауты, lease/heartbeat.
- `config/model_pricing.yaml`: явно фиктивные цены и fake-модели для демонстрации.
- `config/openai_pricing.yaml`: реальные логические primary/economy и тарифы Standard, проверенные 2026-11-03 по [официальной таблице](https://developers.openai.com/api/docs/pricing) и [описанию GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).

Бюджет в YAML рекомендуется задавать строкой, например `"2.00"`. Внутри деньги — Decimal/целые микродоллары, стоимость округляется вверх. Категории cache read/write учитываются отдельно; резерв использует максимальную разрешённую входную цену. Input + output резервируются и по общему лимиту токенов.

Pydantic отклоняет неизвестные поля, отрицательные тарифы, неверный heartbeat, неизвестный routing, слишком большой диапазон, более дорогой fallback и субмикродолларовые бюджеты. `enabled`, `cost_budget.enabled` и `fail_closed` нельзя выключить: библиотека всегда требует общий ledger и жёсткий допуск. Отключение pre_call_worst_case выключает адаптивное сокращение/fallback, но сохраняет атомарную проверку бюджета. Изменение политики применяется к новым run; существующий запуск хранит её fingerprint.

STEER опирается на фактически потраченную сумму, устанавливается один раз и сохраняется между процессами. При нём используется только fallback и максимум 128 output tokens. Дефицит бюджета сначала сокращает output, затем пробует fallback; если не помещается даже минимальный ответ, общий run останавливается. QUEUE имеет ограниченный timeout, REJECT немедленно возвращает ConcurrencyLimitError.

## Настоящий OpenAI (опционально, платно)

```powershell
$env:OPENAI_API_KEY = "your-key"
python examples/openai_demo.py
```

Для bash: `export OPENAI_API_KEY=...`. Автотесты и основное демо эту переменную не используют. Пример не запускался с настоящим ключом. Рабочий адаптер проверяется через настоящий AsyncOpenAI SDK и httpx MockTransport, без сети и оплаты.

Адаптер поддерживает non-streaming text-only Chat Completions, `max_completion_tokens`, `service_tier="default"`, usage/cache categories и отключённые SDK retries. X-Client-Request-Id нужен для корреляции и не является idempotency key провайдера. Другой провайдер добавляется реализацией протокола `providers/base.py`, регистрацией в словаре adapters и ценами в YAML. Адаптер обязан явно ограничивать запрос и классифицировать неопределённый биллинг.

## Ошибки, lease и восстановление

| Ситуация | Поведение |
| --- | --- |
| Redis недоступен до допуска | BudgetStoreUnavailableError, запрос не отправляется |
| Redis недоступен после допуска | Запрос отменяется при ошибке heartbeat, резерв остаётся для сверки |
| Таймаут, отмена, неизвестное исключение | UNKNOWN + сохранённый резерв + общий HALT |
| Процесс аварийно завершился | Lease истекает; reconcile переводит запись в UNKNOWN, деньги не освобождаются |
| Провайдер гарантированно не вызван | Только ProviderNotDispatchedError разрешает нулевой settlement |
| Ответ дороже оценки | Полный известный расход записывается, estimate_overrun HALT |
| Повтор результата | Одинаковый settlement — no-op; отличающийся — SettlementConflictError |
| Повтор запроса с тем же call_id | DuplicateCallError; повторной отправки нет |
| HALT | Все процессы отклоняют следующие вызовы, авторезюма нет |

Heartbeat поддерживается пока LLM-вызов работает. Резерв и живой run не имеют TTL, истекает только lease. Перед новым допуском обёртка запускает reconciliation. Для полностью неактивных запусков вызывайте `reconcile_expired` из своего периодического обслуживающего процесса; отдельный микросервис не нужен.

```python
# Операторская сверка после восстановления Redis/провайдера:
while await ledger.reconcile_expired(run_id):
    pass
call = await ledger.get_call(run_id, call_id)

# Только после проверки провайдерского счёта/идентификатора запроса:
from tokenops_guard.models import Usage
await ledger.resolve_billing(
    run_id, call_id, admin_token=secure_admin_token,
    cost=20000, usage=Usage(input_tokens=100, output_tokens=100),
    evidence="invoice-reference-123",  # Ссылка, без секретов/текста запроса.
)
# Разрешено только после разрешения ВСЕХ резервов. Status остаётся HALTED до этого вызова.
await ledger.resume(run_id, admin_token=secure_admin_token, evidence="incident-123")
# При необходимости оператор явно увеличивает budget (микродоллары) и max_tokens.
```

Нулевой settlement требует доказательства отсутствия списания. Lease expiry и отмена таким доказательством не являются. Late response с проверенным usage может быть списан через settle_budget; он не отменяет HALT. Exhausted step/call caps не сбрасываются операторским resume: завершите расследование и создайте явно новый бизнес-запуск, если необходима новая работа.

`finish()` допускает COMPLETED/FAILED только без незавершённых резервов. Затем оператор может вызвать `expire_terminal_run(..., admin_token=..., ttl_s=86400)` для согласованного TTL всех ключей запуска.

## Наблюдаемость

Доступны `get_run_status`, `get_run_spending`, `get_run_events` (постранично), `get_agent_spending`, `get_model_spending`, `get_call` и `console_summary`. Все money fields возвращаются в микродолларах. Журнал хранит run/agent/call/model/provider, usage, оценки и фактический расход, remaining, время выполнения, STEER/HALT и причины остановки. Время Redis-событий — Unix milliseconds UTC; Python logging использует ISO 8601 UTC.

Включить JSON logging: `logging.basicConfig(level=logging.INFO)`. Приватные prompts, результаты и API-ключи не включаются в события; тексты исключений провайдера не логируются обёрткой. Вызывающий код сам управляет логированием своих исключений.

## Структура

```text
config/                   политики и отдельные таблицы цен
src/tokenops_guard/
  context.py              contextvars и подписанный transport
  config.py, models.py    валидированные модели
  ledger/                 Redis API и атомарный Lua dispatcher
  policies/engine.py      детерминированный shrink/fallback
  providers/              протокол, FakeProvider, AsyncOpenAI
  wrapper.py              admission → execute + heartbeat → settlement
  observability.py        JSON logging и консольная сводка
  demo.py                 сценарии A–E
tests/                    реальные Redis + asyncio + OS processes + mocked SDK
examples/                 короткие демонстрации и платный opt-in пример
docs/architecture.md      источники, состояния, поток данных, риски
```

## Проверки и ограничения

Тесты покрывают context propagation, изоляцию run, атомарные money/token reservations, 5×$0.40 при $1 в asyncio и OS-процессах, одновременные settlement, STEER/fallback, HALT между процессами, потерянный Redis acknowledgement, crash/reconciliation, таймауты, отмену, очередь/отказ, loop guards, cost overrun, TTL и отсутствие приватных данных в audit. CI настроен для Redis 7.4. Фактические результаты и ограничения окружения: [протокол проверки](docs/validation.md).

Инвариант расходов условен: фактическая стоимость должна укладываться в резерв. Неверные цены, недокументированные категории, неограниченный провайдер, потеря Redis-данных или asynchronous failover могут нарушить внешний денежный предел. Система учитывает известную правду, сохраняет неопределённые резервы и останавливает дальнейшие вызовы. Подробнее: [архитектура и ограничения](docs/architecture.md).

Реализация подготовлена по [статье Microsoft](https://commandline.microsoft.com/tokenops-real-time-run-scoped-cost-control-ai-agents/) и [официальному TokenOps](https://github.com/theagentplane/tokenops). От исходного проекта не заявляются производительность или гарантии этой реализации.

## Статус проверки CQA в облачном окружении

Проверены автоматические Python-тесты, сборка Python-пакета и frontend,
исходный browser smoke и отдельный контрактный browser-тест AI-оценки.
Все 65 предоставленных DEV-транскриптов проходят валидацию входного API.
Настоящая генерация Ollama пока не проверена: скачивание `qwen3:4b` блокируется
сетевой политикой окружения: реестр уже доступен, но CDN
`dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com` отвечает Forbidden. Сама Ollama запущена,
список моделей пуст. Требуется применить сохранённые сетевые настройки, загрузить
модель, затем прогнать реальные DEV и новые диалоги. Контрактные тесты с mock-ответом
не являются доказательством точности или работоспособности конкретной LLM.


## Пакетная обработка без браузера

Критерии хранятся в едином `src/cqa/checklist.json`, который используется Python и frontend.
Ключи и подписанные URL не нужны для импорта уже полученного файла.

```bash
# Выполнять из корня репозитория, активировав .venv:
python -m cqa import /path/to/cqa_dev_utf8_fixed.json
python -m cqa serve
# В отдельном терминале, когда модель загружена:
python -m cqa evaluate --limit 1
python -m cqa evaluate
python -m cqa export .runtime/report.json
```

Команда import добавляет диалоги в SQLite без готовых оценок и отклоняет повторные ID.
`evaluate --id ID --force` переоценивает выбранный диалог текущим чек-листом.
Каждый успешный результат сразу сохраняется. Ошибка модели даёт ненулевой exit code,
а проверенные результаты предыдущих диалогов остаются в истории. При конфликте с
браузерными правками пакет останавливается, не перезаписывая чужие изменения.

Начальная настройка контекста допускает все 65 DEV-транскриптов. Перед каждым проходом
система дополнительно проверяет запас контекста; слишком длинный запрос отклоняется,
а не оценивается по усечённому тексту. Оборванные ответы модели не сохраняются.
Успешное исправление JSON обязательно проходит Critic; максимум — три попытки на каждый
из двух этапов. Уверенность LLM не является измеренной точностью.
