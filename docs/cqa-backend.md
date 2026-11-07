# CQA Backend Foundation

Приложение участника 1 находится в `src/cqa/backend/`, инфраструктура — в
`src/cqa/infra/`, опциональные агенты — в `src/cqa/agents/{extractor,classifier}/`.
Используется существующая структура Python-пакета `src/cqa`, чтобы не создавать второй
пакет с тем же именем. TokenOps, frontend и основной AI-модуль сохранены.

## Запуск на Windows

Из корня репозитория, Python 3.11+:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e '.[dev]'
.venv\Scripts\python.exe -m cqa.backend serve
```

Swagger: <http://127.0.0.1:8000/docs>. OpenAPI: `/openapi.json`.
По умолчанию доступны `MockEvaluator`, SQLite и официальный чек-лист `official`, версия 1.
Redis, Docker, GPU, API-ключ и загруженная модель для этого запуска не нужны.
Если в окружении уже есть переменные `LLM_*`, проверьте `LLM_PROVIDER=mock` перед тестом.

Локальный импорт UTF-8/UTF-8 BOM (сервис можно остановить):

```powershell
.venv\Scripts\python.exe -m cqa.backend import 'C:\private\cqa_dev_utf8_fixed.json'
.venv\Scripts\python.exe -m cqa.backend serve
```

Альтернатива после установки: `cqa-backend import FILE`, `cqa-backend serve`.
На Linux используйте `.venv/bin/python` вместо Windows-пути.
Переменные из `.env.example` необходимо экспортировать в окружение процесса;
файл `.env` автоматически не загружается.

```powershell
$env:DATABASE_URL = 'sqlite:///.runtime/cqa-foundation.db'
$env:LLM_PROVIDER = 'mock'
$env:CQA_WORKERS = '2' # параллелизм внутри единственного ASGI-процесса
```

Контейнерный вариант: `docker compose -f compose.foundation.yml up --build`.
Он привязан к loopback, работает от непривилегированного пользователя и хранит БД
в именованном томе. Образ модели не скачивается. Для нового внешнего провайдера
передайте переменные серверу отдельно; текущий Compose намеренно запускает mock.

## Данные и хранение

Принимается официальный envelope `{error, isSuccess: true, data: {dataset_group_id,
total_records, records}}`. `transcript` — массив, роли — `client/operator/bot/system`,
каналы — `agent chat/voice call`, языки — `RU/KZ/EN`.
`total_records` обязан совпасть с длиной массива. Размер DEV не навязывается другим группам.
Чаты сохраняют исходный `MM:SS`, звонки — ISO timestamp с часовым поясом и дробной частью.
У звонка обязателен HTTPS `audio_url`. Сервер не скачивает аудио.

`message_id = "msg_" + sha256(conversation_id + NUL + zero_based_index)`.
Порядок реплик и исходная запись сохраняются в БД. Повтор идентичного импорта пропускается.
Конфликтующий ID отклоняет весь импорт с 409, сохраняя исторические данные.
ID диалога глобален для базы: при пересечении разных групп потребуется согласовать
разделение ID или отдельную БД, а не перезаписывать прежнюю группу.

Каждая версия чек-листа — отдельная строка; API изменения старой версии отсутствует.
Для обновления отправляется новый полный чек-лист с `base_version` последней версии.
Начальные ID критериев `"1"`…`"8"` сохранены для совместимости с текущим frontend/AI;
это критерии 01…08 из задания. Их веса, N/A и ступени берутся из существующего
`src/cqa/checklist.json`. Отдельная конкурирующая формула расчёта не добавляется:
`ExistingScoringAdapter` вызывает `cqa.service.score`.

## Контракт frontend

Все URL ниже начинаются с `/api`. Даты — строки ISO 8601 UTC, версии — целые числа.
Ответы ошибок: `{detail: string}`; ошибки входной валидации дополнительно содержат
`errors: [{loc, type}]` без приватного `input` и текста исключения провайдера.
Коды: 201 создание, 202 принятое задание, 404 неизвестный ресурс/группа,
409 конфликт версии/данных/пересмотра, 422 неверный ввод, 502 ошибка организаторов,
503 ошибка БД. CORS — только `CQA_CORS_ORIGINS`, без credentials.

| Метод и URL | Вход / результат |
| --- | --- |
| `GET /health` | `status`, `provider`, `model`, `is_mock`; проверяет БД, не готовность реальной LLM |
| `POST /datasets/import` | `{source:"local", payload:OFFICIAL_ENVELOPE}` или `{source:"organizer",group_id:"DEV"}` → `dataset_group_id,total_records,imported,skipped` |
| `GET /conversations` | Массив; фильтры `group_id,language,channel`, `offset=0,limit=100` (макс. 1000) |
| `GET /conversations/{id}` | Поля Conversation + `messages`; исходный payload остаётся на сервере |
| `GET /checklists` | Последняя версия каждого чек-листа |
| `POST /checklists` | `{checklist_id,base_version?,criteria,sections?}` → полная созданная версия |
| `GET /checklists/{id}` | Последняя версия |
| `GET /checklists/{id}/versions/{version}` | Неизменяемая версия |
| `POST /evaluations` | `{conversation_id,checklist_id,checklist_version,retry_failed?:false}` → Job |
| `GET /evaluation-jobs/{id}` | Job и `evaluation_id` после завершения |
| `GET /evaluations/{id}` | Evaluation, исходный `result_json`, текущий `final_result_json`, `review_revision` |
| `POST /appeals` | `{evaluation_id,criterion_id,comment}` → Appeal |
| `GET /appeals/{id}` | Appeal |
| `POST /appeals/{id}/review` | Решение проверяющего, описанное ниже |
| `GET /evaluations/{id}/reviews` | История, упорядоченная по `revision`, исходные и окончательные snapshots |

Conversation: `conversation_id,dataset_group_id,channel,language,audio_url,imported_at`.
Message: `message_id,message_index,speaker,timestamp_original,text`.
Criterion сохраняет существующий словарь полей:
`id,title,description,weight,type,scale,naAllowed,naCondition`.
Job: `job_id,conversation_id,checklist_id,checklist_version,status,error_message,attempts,
evaluation_id,created_at,updated_at`. Статусы: `pending → running → completed/failed`.
Evaluation содержит также `job_id,evaluator_name,model_name,prompt_version,is_mock,created_at`.
В `result_json`: `findings,is_mock,metadata,score,critical,stages`.

Пример создания задания (полученный `job_id` опрашивать до terminal status):

```json
{"conversation_id":"p1-ru-001","checklist_id":"official","checklist_version":1}
```

Пример принятой апелляции:

```json
{
  "decision": "accepted",
  "reason": "Проверяющий подтвердил действие по исходной реплике",
  "base_revision": 0,
  "replacement": {
    "criterion_id": "1",
    "answer": "Да",
    "explanation": "Причина решения проверяющего",
    "message_ids": ["ID_ИЗ_ИСХОДНОГО_ДИАЛОГА"],
    "checked_message_ids": [],
    "na_reason": null
  }
}
```

Для отказа: `decision:"rejected"`, причина, текущий `base_revision`, без `replacement`.
Нельзя пересмотреть закрытую апелляцию повторно. Неверная ревизия возвращает 409.
Принятое решение проходит ту же валидацию и Scoring adapter с исторической версией
чек-листа. Исходный `result_json` не обновляется; решения накапливаются последовательно.

**Подключение существующего интерфейса:** текущие `cqa.api` и браузерный workspace остаются
отдельным прототипом со старым контрактом. Новый foundation не мигрирует автоматически
их SQLite/localStorage и не заменяет `/api/evaluate` или `/api/workspace`.
Frontend-разработчик должен подключить перечисленные REST endpoints и хранить ID jobs/evaluations,
маппируя поля сообщений и результатов на существующие view models. При параллельном запуске
назначьте приложениям разные порты. Реальные звонки не импортируйте в публичный static demo.

## Контракт AI-разработчика

Публичные типы: `ConversationDetail`, `ChecklistView` из `cqa.backend.schemas` и
`EvaluationResult`, `Finding`, `Evaluator`, `Scorer`, `Critic` из
`cqa.infra.orchestrator.pipeline`.

```python
class TeamEvaluator:
    name = "TeamEvaluator"
    model = "explicit-model-name"
    is_mock = False

    def configuration(self):
        return {"name": self.name, "model": self.model, "version": 1}

    async def evaluate_conversation(self, conversation, checklist):
        # Полный разговор, реальные ID, роли, язык, канал и конкретная версия.
        return EvaluationResult(findings=[...], metadata={"prompt_version": "team-v1"})

pipeline = Pipeline(evaluator=TeamEvaluator(), scorer=TeamScoringAdapter())
app = create_app(settings, pipeline=pipeline)
```

Scorer реализует `configuration() -> dict` и синхронный `score(checklist,result) -> dict`
с полями `score: float|null, critical: bool`. Его конфигурация обязана меняться вместе
с реализацией/правилами. Evaluator возвращает ровно один Finding на каждый критерий:
`criterion_id,answer,explanation,message_ids,checked_message_ids,na_reason`.
Числовой ответ — только ступень из `scale`; `N/A` — только при `naAllowed` и непустом
`na_reason`. Для отсутствия действия нужен проверенный участок; ссылки проверяются
по исходным ID. Подтверждение семантики остаётся ответственностью Evaluator/Critic.

Critic: `configuration()` и `async review(conversation,checklist,result)`.
Extractor: `configuration()` и `async extract(conversation)`.
Classifier: `configuration()` и `async classify(extraction,categories)`.
Их экземпляры передаются в `Pipeline`; все необязательны. Базовые реализации извлекают
только роли/счётчики/канал/язык и сопоставляют переданные категории, не утверждают
семантическую корректность консультации. Основной Evaluator всегда получает полный разговор.

MockEvaluator возвращает синтетические ответы с `is_mock=true`, без выдуманных цитат.
Он не измеряет качество. `ProviderEvaluator` адаптирует существующие `RULES`, `Analysis`
и `validate_analysis` участника AI; проверяет точные цитаты перед преобразованием в Finding.
Это один проход; обязательный Critic реального пайплайна подключается отдельно.

## Провайдеры и контрольные данные

По умолчанию `LLM_PROVIDER=mock`. Groq/совместимый API:

```powershell
$env:LLM_PROVIDER = 'openai_compatible'
$env:LLM_BASE_URL = 'https://api.groq.com/openai/v1'
$env:LLM_MODEL = 'ТОЧНОЕ_ИМЯ_ДОСТУПНОЙ_МОДЕЛИ'
$env:LLM_API_KEY = 'ЛОКАЛЬНЫЙ_СЕКРЕТ'
# Только после разрешения организаторов на внешнюю обработку данных:
$env:CQA_ALLOW_EXTERNAL_DATA = 'true'
```

Бесплатные лимиты не гарантируются. Реальный вызов производится только при задании.
Для Ollama: установите и запустите её самостоятельно, осознанно загрузите подходящую
модель, задайте `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://127.0.0.1:11434`, `LLM_MODEL`.
Автозагрузки модели нет. Следует проверить доступный контекст (адаптер запрашивает 65536),
RAM и увеличить `CQA_JOB_TIMEOUT` при необходимости. Удалённый сервер должен быть доверенным.
Настоящая генерация, точность RU/KZ/EN, токены и лимиты конкретных моделей требуют
отдельного прогона с разрешёнными данными. Тесты используют HTTP mock transport.

Для API организаторов задайте полный `FREEDOM_DEV_API_URL` или `FREEDOM_CONTROL_API_URL`.
Ссылки используются без изменения query, перенаправления запрещены; разрешён только
HTTPS-домен `environment.api.powerplatform.com` и его поддомены.
`source:"organizer",group_id:"CONTROL"` выбирает отдельно настроенный полный URL.
Ответ обязан содержать ту же группу. Изменение `group_id` внутри старой подписи не выполняется.
Для иной группы добавьте её полный URL в серверный `Settings.organizer_urls` через app factory;
локальный envelope с новым `dataset_group_id` работает без изменения кода.

## Надёжность, ограничения и развёртывание

Очередь — строки БД, а не память процесса. Worker claim выполняется условным UPDATE;
завершение job и сохранение evaluation — одной транзакцией. Уникальные cache key и job_id
результата предотвращают дубликаты. Ключ учитывает полный текст/метаданные, версию/конфигурацию
чек-листа, prompt, модель/provider, конфигурацию стадий и реализацию scorer.
После смены конфигурации старое задание завершается ошибкой; создайте новое задание.
Ошибочное задание повторяется только явным `retry_failed:true`.

Один ASGI-процесс на SQLite-файл, `CQA_WORKERS` — размер его пула. Файловая блокировка
запрещает второй worker-процесс. При старте running возвращаются в pending;
после трёх аварийных попыток — failed. Завершённые результаты не пересчитываются.
Shutdown отменяет только управляемые задачи worker; незавершённые строки остаются в БД.
После сбоя внешний запрос может повториться: гарантируется однократное сохранение,
а не однократный вызов/списание у провайдера.

HTTP timeout, максимум три попытки с exponential backoff для network/timeout/429/5xx;
401/403 не повторяются. `CQA_JOB_TIMEOUT` ограничивает всё задание.
В журнале только статус/тип ошибки; HTTP URL редактируются. В ответах нет подписанного
organizer URL или текста исключения. Аудио URL возвращается как часть диалога по требованию ТЗ.

SQLAlchemy допускает другую СУБД, но текущий встроенный worker требует файловую SQLite.
Для PostgreSQL понадобятся драйвер, миграции и внешний worker/claim с lease/блокировками.
Автоматических миграций схемы пока нет: для существующей foundation-БД используйте
резервную копию и явную миграцию перед обновлением структуры. Старую workspace-БД не удаляйте.

Перед публичным размещением: проверить разрешение на хранение/обработку звонков,
закрыть публичный доступ к данным (сетевой периметр или отдельный слой доступа), TLS,
лимиты размера тела/частоты/очереди, резервное копирование с проверкой восстановления,
миграции, ограничения хранения, мониторинг worker и защиту секретов.
Обязательная авторизация в сам прототип не добавлена согласно заданию.

## Проверки

```powershell
.venv\Scripts\python.exe -m pytest tests/cqa -q
.venv\Scripts\ruff.exe check src tests examples
.venv\Scripts\ruff.exe format --check src tests examples
# Опционально: приватный реальный DEV, содержимое не выводится и не публикуется.
$env:CQA_TEST_DEV_FILE = 'C:\private\cqa_dev_utf8_fixed.json'
.venv\Scripts\python.exe -m pytest tests/cqa/test_foundation_data.py -q
```

Синтетические проверки покрывают распределение 65/60/5, 35/15/15, стабильные ID,
исходные timestamps/audio, повторный/атомарный импорт, версии, N/A/ступени,
mock, retries/timeouts/concurrency, восстановление и апелляции. Это не проверка
реального DEV или точности модели. Полный `pytest` также требует Redis для старого TokenOps.
Фактический прогон и ограничения окружения: [отчёт](cqa-backend-validation.md).
