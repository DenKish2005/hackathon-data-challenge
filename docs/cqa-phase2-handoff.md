# Phase 2: точный integration handoff

## Участнику №3: React

Компоненты не изменены. Существующие вызовы работают на том же backend:

| Endpoint | Поведение |
| --- | --- |
| `GET /api/workspace` | `{revision,data}`; canonical диалоги, текущие критерии, результаты, апелляции |
| `PUT /api/workspace` | `{revision,data}` → `{revision}`; 409 при конфликте; атомарная запись |
| `POST /api/evaluate` | Старый inline контракт → общий durable job → совместимый результат |
| `GET /api/history/{conversation_id}` | Оригинальные оценки Foundation в старом формате |
| `GET /api/organizer?group_id=DEV` | Полный настроенный URL без изменения подписи; импорт + исходный envelope |

Пример текущего `POST /api/evaluate`:

```json
{
  "conversation_id":"synthetic-001",
  "language":"EN",
  "version":1,
  "checklist_id":"official",
  "force":false,
  "messages":[{"id":"m1","role":"operator","text":"Hello! My name is Anna.","time":"00:01"}],
  "criteria":[{"id":"1","title":"Greeting","description":"Operator greets and introduces themselves","weight":10,"type":"binary","scale":[],"naAllowed":false,"naCondition":""}]
}
```

`criteria` должны в точности совпадать с выбранной сохранённой версией;
пример выше иллюстрирует форму и требует такого же сохранённого чек-листа.
`checklist_id` необязателен для старого UI. Без него backend связывает UI-version
с неизменяемой Foundation-версией; существующая версия с другими критериями → 409.
Новая offline UI-version может ссылаться на иной canonical номер: используйте
возвращённые `foundationChecklistId/foundationChecklistVersion` для новых REST-вызовов.
`messages` проверяются против сохранённого источника; язык/порядок/роли/текст/время
не могут подменить импортированный разговор. В модели используются canonical
message IDs; старые UI IDs возвращаются в совместимых findings.

Основные поля ответа:

```json
{
  "evaluationId":"SAVED_ID","jobId":"JOB_ID","conversation_id":"synthetic-001",
  "model":"qwen3:4b","is_mock":false,"checklistVersion":1,
  "foundationChecklistId":"official","foundationChecklistVersion":1,
  "criteriaSnapshot":[],"results":[],"score":75.0,"critical":false,
  "tokens":4350,"passes":2,"cached":false,"reviewRevision":0,
  "metadata":{"prompt_version":"foundation-v1","calls":[]}
}
```

Списки в примере сокращены; каждый `results[]` содержит прежние
`criterionId,answer,reason,evidenceId,quote,checkedMessageIds,confidence`.
При отсутствии reported usage `tokens:null`; неизвестная confidence тоже null.
Mock имеет `is_mock:true`, явные synthetic explanations, без придуманных цитат.

Точные рекомендуемые изменения владельцу UI:

1. `EvaluationPanel.jsx`: название провайдера брать из `/api/health.provider`,
   модель из `model`. Статусы: mock / configured / ready / model_unavailable.
   `ready` означает наличие модели в Ollama, а не гарантию успешной генерации.
   Показывать mock отдельной меткой. Текст «два прохода» заменить фактическим `passes`.
2. `App.jsx:applyEvaluation` и export: определять synthetic по `is_mock`, а провайдера
   по metadata; историческое `source:"ollama"` используется адаптером для старой
   совместимости и не является новым provider contract. Учитывать
   `originalResults`/`originalScore` из workspace при восстановлении после апелляции.
3. Добавить выбор `GET /api/checklists/{id}/versions/{version}` (историческая версия)
   и передавать `checklist_id`/version и её `criteria` вместе. Текущий редактор уже
   создаёт версии через autosave; старые snapshot результатов не редактировать.
4. Для длинной партии заменить ожидание одного POST на `POST /api/evaluations`
   → polling `/api/evaluation-jobs/{id}` → GET `/api/evaluations/{id}`.
   202 — job принят, completed — оценка сохранена, failed — показывать error_message.
   504 старого adapter возвращает job_id внутри detail: job не отменён, продолжить polling.
5. Для нескольких пользователей перейти от общего autosave к явным
   POST `/api/appeals` и `/api/appeals/{id}/review`, передавая `base_revision`.
   Текущая старая форма decision переводится адаптером в accepted review; она не
   различает отдельный rejected workflow. Новая форма должна отправлять decision
   accepted/rejected и replacement только для accepted.
6. После смены модели/checklist/reviews обновлять серверный workspace, не применять
   сохранённый балл от другого job. Показывать `result_json` как оригинал, а
   `final_result_json` как текущий итог. На 409 сохранять локальный экспорт и reload.

## Участнику №2: Evaluator/Critic/Scoring

Контракт не изменён:

```python
async def evaluate_conversation(conversation, checklist) -> EvaluationResult: ...
```

`ConversationDetail` содержит полный transcript, стабильные IDs, роли
client/operator/bot/system, language RU/KZ/EN, channel agent chat/voice call,
исходные timestamps и audio_url. `ChecklistView` — конкретная сохранённая версия.
Нужно вернуть ровно один Finding на критерий, объяснение, message_ids либо
checked_message_ids, и na_reason для N/A. Проверки инфраструктуры не доказывают
семантическую правильность; это ответственность командного Evaluator/Critic.

Временный реальный путь — ProviderEvaluator; он использует существующие RULES,
Analysis, validate_analysis и точные цитаты. ProviderCritic использует перенесённую
без изменения CRITIC_RULES из существующего кода. Формула scoring не дублируется.

```python
pipeline = Pipeline(
    evaluator=TeamEvaluator(),
    scorer=TeamScoringAdapter(),
    critic=TeamCritic(),
)
app = create_app(settings, pipeline=pipeline)
```

Каждая стадия реализует versioned `configuration()`, включая модель, prompt,
настройки и изменяемую реализацию. Это часть cache key. Не заменяйте отказ LLM
на MockEvaluator. Provider.generate остаётся dict-совместимым; реальные адаптеры
возвращают GeneratedJSON с per-call `.metadata` (usage/duration/provider/model).
Текущий ProviderEvaluator сохраняет также валидированный Analysis и confidence.

Не интегрированы отдельные командные Evaluator/Critic и независимая эталонная
оценка качества. Фактический live-прогон подтверждает инфраструктуру, не accuracy.
