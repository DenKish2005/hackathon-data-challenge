# Phase 3: локальный запуск и демонстрация

Основной вариант — локальный Ollama, один FastAPI entry point с React static,
SQLite на постоянном диске. Внешние платные API для проверки не используются.

## Windows: одна команда после установки

Требуются Python 3.11+, Node 20.19+, установленная Ollama и вручную установленная
`qwen3:4b`. Модель автоматически не скачивается. Из корня проекта:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File examples/cqa_demo.ps1
```

Открыть <http://127.0.0.1:8000>. Повторный запуск без повторной сборки:

```powershell
powershell -ExecutionPolicy Bypass -File examples/cqa_demo.ps1 -SkipBuild
```

Скрипт проверяет сборку React, 512 MiB свободного места, доступность Ollama и
наличие модели; показывает доступные RAM/VRAM. Проверка модели — `/api/tags`,
она не гарантирует успешную генерацию. Отсутствие GPU допускает CPU inference,
скорость зависит от машины. RAM измеряется для всей системы; VRAM — сумма GPU.

Настройки demo: context 16384, output 4096, один worker и один HTTP LLM-запрос,
timeout LLM 600 s / job 1250 s. Они переопределяются env до запуска.
Critic выключен явно; `-Critic` включает его и требует подходящего контекста.
Для полного Critic сначала воспроизведите замер с context 24576, затем задайте
`$env:LLM_CONTEXT_SIZE='24576'`. На 6 GiB возможен CPU offload.
Инструкции Evaluator/Critic и scoring не изменялись.

БД по умолчанию `.runtime/cqa-demo.db`; при повторном запуске используется та же.
Для другой БД задайте `DATABASE_URL`. Не запускайте два backend на одном SQLite.
Перед резервным копированием остановите приложение; скопируйте `.db` вместе с
существующими `-wal`/`-shm`, либо используйте SQLite backup API. Не копируйте
отдельный файл активной WAL-БД как гарантированно полную резервную копию.
Остановка Ctrl+C сохраняет завершённые результаты; running jobs восстанавливаются.

Ручной запуск с уже экспортированными переменными:

```powershell
.venv\Scripts\python -m cqa doctor
.venv\Scripts\python -m cqa serve
```

`/api/health` проверяет БД и сообщает provider/model; `/api/ready` возвращает 503,
если настроенная Ollama/модель недоступна или managed worker неожиданно завершился.
При `worker_unavailable` устраните причину и перезапустите backend с той же БД.
Для внешнего API статус `configured`
означает только конфигурацию — inference не вызывается для проверки готовности.
Python не загружает `.env` автоматически. Подписанные URL и API keys — только
в локальном окружении/приватных файлах, не в командных аргументах или frontend.

## Партия и контрольный набор

Локальный JSON envelope сохраняет настоящий `dataset_group_id`:

```powershell
.venv\Scripts\python -m cqa import 'C:\private\control.json'
.venv\Scripts\python -m cqa evaluate --group-id CONTROL-EXACT --parallel 1 --timeout 1300 --report .runtime/control-report.json
# После прерывания: та же команда, неизменённые completed jobs берутся из кэша.
# Только failed из предыдущего отчёта, тот же checklist/version:
.venv\Scripts\python -m cqa evaluate --group-id CONTROL-EXACT --failed-only --report .runtime/control-report.json --timeout 1300
.venv\Scripts\python -m cqa export .runtime/private-results.json
```

Backend должен работать при evaluate. `--parallel` ограничивает число незавершённых
заданий, поданных данным CLI (1–16), `LLM_CONCURRENCY` — реальную конкуренцию модели,
`CQA_WORKERS` — workers. Для 6 GiB начните с 1. Несколько CLI делят общую очередь.
`--checklist-id` / `--version` фиксируют версию партии. Изменение текущего чек-листа
не меняет уже запущенную партию. `--force` создаёт новые оценки, старые сохраняются.
`--force` нельзя сочетать с `--failed-only`.

JSON/CSV записываются атомарной заменой после каждого ответа. Отчёт содержит ID,
статусы, баллы и telemetry; тексты/URL отсутствуют. Отчёт описывает текущий запуск;
failed-only обновляет его результатами выбранных повторов. Сохраните копию отчёта,
если нужна история запусков. SQLite — источник восстановления, report не заменяет БД.
Ctrl+C останавливает локальный polling; принятые сервером jobs продолжают работать.
Код выхода 130 — прерывание, 1 — есть failed/unfinished, 0 — все выбранные завершены.
ETA для 65 считается только по фактическим новым successful jobs, cached jobs не
создают искусственную пропускную способность. Неизвестные токены остаются null.

Новый произвольный ID группы настраивается без изменения кода. В приватном JSON
файле, например `C:\private\organizer-urls.json`, сохраните словарь
`{"EXACT_GROUP_ID":"FULL_SIGNED_URL_FROM_ORGANIZERS"}`. Затем:

```powershell
$env:FREEDOM_DATASET_URLS_FILE = 'C:\private\organizer-urls.json'
.venv\Scripts\python -m cqa import --organizer EXACT_GROUP_ID
```

Перезапустите backend с этой же переменной для импорта через API/UI.
Существующие `FREEDOM_DEV_API_URL` / `FREEDOM_CONTROL_API_URL` поддерживаются.
URL используется целиком, подпись и query не переписываются. Группа в ответе
должна точно совпасть с выбранной. Ошибки импорта откатывают транзакцию; иной
разговор с уже занятым ID вызывает 409, не перезаписывает источник.

## Docker Compose

```powershell
$env:LLM_PROVIDER='ollama'
$env:LLM_BASE_URL='http://host.docker.internal:11434'
$env:LLM_MODEL='qwen3:4b'
$env:LLM_CONTEXT_SIZE='16384'
$env:LLM_OUTPUT_LIMIT='4096'
$env:LLM_TIMEOUT='600'
$env:CQA_JOB_TIMEOUT='1250'
$env:CQA_WORKERS='1'
$env:CQA_ENABLE_CRITIC='false'
docker compose -f compose.foundation.yml config --quiet
docker compose -f compose.foundation.yml up --build -d
docker compose -f compose.foundation.yml ps
curl.exe --fail http://127.0.0.1:8000/api/ready
docker compose -f compose.foundation.yml logs --tail 50 backend
```

Dockerfile уже собирает React через Node stage и Python backend, запускается
пользователем `cqa`. Named volume `cqa-foundation` хранит `/data/cqa-foundation.db`.
Публикуется только loopback port 8000. Healthcheck использует `/api/ready`.
Ollama хоста должна быть доступна контейнеру через host gateway; не открывайте
11434 в интернет. На Linux может понадобиться доступ Ollama на host bridge
с firewall, разрешающим только локальную Docker-сеть.

На этой машине Docker Engine недоступен. Config проверен; build/run контейнера
не подтверждены. На машине с Engine обязательно выполнить команды выше, затем
синтетическую оценку, `docker compose restart backend`, проверить старый result ID,
и повторный batch с тем же volume. Не выполнять `down -v` для рабочей БД.
Для произвольных групп в Docker смонтируйте приватный URL JSON read-only и задайте
`FREEDOM_DATASET_URLS_FILE` внутри контейнера через локальный compose override.

## Сетевой показ

Основной показ — локальный экран. Для необязательного публичного показа используйте
отдельную пустую БД и только синтетические данные. Приложение не имеет авторизации:
любой имеющий URL сможет читать/менять workspace и запускать модель.

После ручной установки `cloudflared` возможен временный tunnel только к FastAPI:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Quick Tunnel даёт временный URL без аккаунта/домена, предназначен для тестирования,
без SLA; см. [официальную документацию Cloudflare](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
Туннель здесь не открывался. Реальный DEV/CONTROL не публиковать без разрешения
организаторов и контроля доступа. Ollama через tunnel не публиковать.
Старый inline `/api/evaluate` может ждать дольше таймаута сетевого proxy: для
удалённой демонстрации нужен переход UI на durable POST + polling (handoff).
