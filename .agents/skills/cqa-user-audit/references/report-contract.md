# Контракт отчёта для последующего Codex Fix

## Файлы

- `REPORT.md` — читаемый человеком итог с измеренными фактами и ссылками на evidence.
- `BUGS.json` — объект `{schema_version,run,bugs}`.
- `ACTION_TRACE.jsonl` — JSON-объект на **каждом** шаге браузера.
- `COVERAGE.csv` — одна строка на каждый test-matrix ID и найденный exploratory case.
- `FIX_PROMPT.md` — отдельный рабочий документ для исправляющего Codex.
- `EVIDENCE/` — скриншоты/trace/log snippets **только на синтетических данных** и без секретов.

## BUGS.json

```json
{
  "schema_version": "1.0",
  "run": {
    "id": "20261107T190000Z",
    "base_url": "http://127.0.0.1:8000",
    "commit": "COMMIT_HASH",
    "mode": "INTEGRATION",
    "browser": "Chromium version",
    "os": "Windows",
    "data_classification": "synthetic"
  },
  "bugs": [{
    "id": "CQA-BUG-001",
    "title": "Повторное нажатие создаёт дублированную апелляцию",
    "severity": "MAJOR",
    "priority": "P1",
    "scenario_ids": ["APPEAL-06"],
    "mode": "INTEGRATION",
    "preconditions": "Synthetic conversation A, existing evaluation, appeal form open",
    "steps": ["Открыть ...", "Нажать ... дважды"],
    "expected": "Одна апелляция и один статус сохранения",
    "actual": "Отобразились две апелляции с разными IDs",
    "attempts": 2,
    "reproduced": "reproduced",
    "evidence": ["EVIDENCE/CQA-BUG-001.png"],
    "trace_steps": [12,13,14],
    "network_observation": "POST /api/appeals: два 201; sanitized",
    "console_observation": "none",
    "impact": "Дублирование рассмотрения",
    "root_cause_hypothesis": "Возможен пропуск блокировки повторной отправки",
    "hypothesis_confidence": "low",
    "candidate_files": ["frontend/src/App.jsx"],
    "suggested_regression_test": "Double-click submit returns one appeal and one persisted record"
  }]
}
```

Пример выше — **иллюстрация**, не обнаруженный баг. Не копируй его в реальные находки без воспроизведения.

## ACTION_TRACE.jsonl

Каждая строка:

```json
{"step":12,"at":"2026-11-07T19:30:01Z","scenario_id":"APPEAL-06","mode":"INTEGRATION","page":"/","action":"double-click","target":"button: Отправить на пересмотр","input_summary":"synthetic reason","before":"апелляция не создана","expected":"одна апелляция","observed":"две апелляции","verdict":"FAIL","evidence":["EVIDENCE/CQA-BUG-001.png"],"bug_ids":["CQA-BUG-001"]}
```

Записывай PASS, FAIL, BLOCKED (и программно зафиксированные skip), а не только FAIL. Номера `step` монотонны.

## COVERAGE.csv

Поля: `scenario_id,priority,category,mode,status,executed_at,notes,bug_ids,evidence`.
`status`: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`.

## Severity

- BLOCKER: критичный стоп-фактор демонстрации, нельзя выполнить основной user journey.
- CRITICAL: потеря/перепутывание данных, недостоверный финальный балл, опасная утечка.
- MAJOR: существенная поломка основной функции, есть обходной путь.
- MINOR: краевая ошибка, не ломает основную работу.
- COSMETIC: внешний вид без функционального ущерба.

Приоритет P0/P1/P2 может отличаться от severity из-за дедлайна и распространённости.

## Корректность наблюдений

- `expected`: из ТЗ, формулы, официальной документации или пользовательского контракта. Если спорно, пометь как `UX expectation`, а не как формальное нарушение.
- `actual`: конкретный screenshot/UI text/status/DB value. Не заполняй гипотезой.
- `root_cause_hypothesis`: предположение. `hypothesis_confidence` не может выдавать догадку за факт. Если нет доказательств, пиши `unknown`.
- `evidence`: относительный путь внутри пакета, не абсолютная ссылка на приватный компьютер.
- Все `BUGS.json` на момент передачи должны соответствовать текущему commit; если тест позже стал PASS — пометь fixed-in-new-run в новом отчёте, не стирай исходные наблюдения.
- Перед передачей исправляющему Codex обезличь screenshots/quotes/logs и очисти секреты; real source transcripts и private dataset никогда не включай в отчёт.
