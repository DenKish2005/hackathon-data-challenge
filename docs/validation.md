# Результаты проверки реализации

Проверка выполнена 2026-11-03 в текущем рабочем пространстве на Windows, Python 3.12.10, Redis 5.0.14.1 (настоящий локальный сервер, порт 16379), OpenAI Python SDK 2.54.0, redis-py 6.4.0. Для Docker/CI конфигурация использует Redis 7.4.

## Выполнено

```powershell
$env:TEST_REDIS_URL = "redis://127.0.0.1:16379/15"
.venv/Scripts/python.exe -m pytest -q --tb=short
# 47 passed in 16.44s

$env:REDIS_URL = "redis://127.0.0.1:16379/0"
.venv/Scripts/python.exe -m tokenops_guard.demo --scenario all

.venv/Scripts/ruff.exe check src tests examples
# All checks passed!
.venv/Scripts/ruff.exe format --check src tests examples
# 29 files already formatted

docker compose config --quiet
# exit 0

$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
uv build --wheel --offline
# Successfully built dist/tokenops_guard-0.1.0-py3-none-any.whl
```

Дополнительно проверены содержимое wheel (включая `ledger/scripts/ledger.lua`), валидация реальной OpenAI-конфигурации и отсутствие TODO/FIXME/NotImplemented в реализации.

| Демо | Наблюдаемый результат |
| --- | --- |
| A | COMPLETED, 3 вызова, 4 шага с локальным tool, spent $0.60 |
| B | primary на вызовах 1–4, economy на 5–6; один STEER; spent $0.84 |
| C | HALTED, spent $0, provider dispatches 0 |
| D | HALTED progress_guard, предупреждение перед остановкой, 4 provider dispatches |
| E | 5 отдельных процессов, 2 допуска, общий резерв $0.80; после settlement COMPLETED, spent $0.80 |

Тесты проверяли реальные Lua-операции и межпроцессные подключения к одному Redis. OpenAI SDK тестировался через httpx MockTransport; платных вызовов не было. Тесты сбоев heartbeat/settlement и потерянного Redis acknowledgement используют направленную инъекцию отказов; процесс агента действительно аварийно завершается через os._exit в crash-тесте.

## Ограничения проверки окружением

Docker Desktop установлен, но Docker Engine недоступен: подключение к `dockerDesktopLinuxEngine` возвращает отсутствие named pipe; WSL status возвращает `Wsl/E_ACCESSDENIED`. Поэтому Docker image build, запуск Compose и Linux CI в этом окружении **не выполнялись**. Проверена синтаксическая корректность Compose; функциональные проверки выполнены локально.

Локальный Redis for Windows загружен из [релиза tporadowski/redis](https://github.com/tporadowski/redis/releases/tag/v5.0.14.1), бинарные файлы хранятся только в игнорируемой `.runtime/`. Это временная среда тестов, а не рекомендуемый production-сервер. Тестовый сервер работает только на 127.0.0.1:16379, без persistence; проверка потери/восстановления данных самого Redis не проводилась.

Не проверялись доступность реальных моделей в аккаунте, реальный провайдерский счёт, Redis Cluster/failover, производительность и запуск под Python 3.11/3.13. Для проверки на рекомендуемом Redis 7.4 при доступном Docker:

```sh
docker compose up -d redis
docker compose run --build --rm tests
docker compose run --build --rm demo
```
