# Graph Report - Hackathon  (2026-11-07)

## Corpus Check
- Corpus is ~47,222 words - fits in a single context window. You may not need a graph.

## Summary
- 1177 nodes · 2975 edges · 62 communities (49 shown, 13 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 520 edges (avg confidence: 0.91)
- Token cost: unavailable — the runtime does not expose host-agent usage; zero counters in local cost.json are placeholders.

## Community Hubs (Navigation)
- Оценка диалогов CQA
- Схемы и API CQA
- Настройки и тесты API
- Провайдеры языковых моделей
- Расходы и ответы LLM
- Проверки резервирования бюджета
- Авторизация контекста запуска
- Политики ограничений TokenOps
- Демонстрации параллельного выполнения
- Публикация GitHub Pages
- Апелляции и модели данных
- Валидация настроек TokenOps
- Хранилище бюджета Redis
- Контейнеры Foundation backend
- Контейнеры Redis и демонстраций
- Чеклисты и совместимость
- Очередь заданий оценки
- Тарифы моделей OpenAI
- Основной интерфейс React
- Зависимости и сборка frontend
- Управляемые вызовы LLM
- Чеклисты и совместимость
- Маршруты и жизненный цикл
- Руководство по TokenOps
- Импорт и экспорт workspace
- Архитектура резервирования бюджета
- Контракты и интеграция Phase2
- Автоматические проверки Python
- Тестовые тарифы моделей
- Импорт наборов диалогов
- Документация приложения Phase2
- Расчёт оценок frontend
- Контейнер локальной Ollama
- Экран критериев оценки
- Исходный экран анализа
- Атомарные операции Lua
- Экран анализа диалога
- Мобильная очередь диалогов
- Документация интерфейса Freedom
- Мобильный контроль качества
- Панель показателей качества
- Таблица диалогов Freedom
- Просмотр доказательств оценки
- Контракты и интеграция Phase2
- Инициализация базы данных
- Аудит перехода Foundation
- Экран подачи апелляции
- Панель запуска оценки
- Команды сборки frontend
- Адаптер детерминированного скоринга
- Проверка исходной Foundation
- Логотип Freedom CQA
- Синхронизация рабочего пространства
- Метаданные пакета TokenOps

## God Nodes (most connected - your core abstractions)
1. `RedisLedger` - 61 edges
2. `create_app()` - 56 edges
3. `GovernedLLMClient` - 48 edges
4. `Usage` - 34 edges
5. `RunContext` - 31 edges
6. `FakeProvider` - 31 edges
7. `configured()` - 28 edges
8. `Schema` - 27 edges
9. `bind_run()` - 26 edges
10. `Evaluation` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Shared HALT and Billing Recovery` --conceptually_related_to--> `Single-process SQLite Worker`  [INFERRED]
  README.md → docs/cqa-backend.md
- `Historical Criteria Snapshot` --conceptually_related_to--> `Immutable Checklist Versions`  [INFERRED]
  frontend/README.md → docs/cqa-backend.md
- `main()` --calls--> `load_settings()`  [INFERRED]
  examples/openai_demo.py → src/tokenops_guard/config.py
- `main()` --calls--> `bind_run()`  [INFERRED]
  examples/openai_demo.py → src/tokenops_guard/context.py
- `main()` --calls--> `RedisLedger`  [INFERRED]
  examples/openai_demo.py → src/tokenops_guard/ledger/redis_ledger.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Shared run enforcement flow** — readme_runcontext, readme_governedllmclient, readme_redisledger, docs_architecture_atomic_reservations, docs_architecture_idempotent_settlement [EXTRACTED 1.00]
- **Uncertain billing recovery flow** — docs_architecture_leases_heartbeat, docs_architecture_unknown_billing, readme_halt, readme_operator_recovery, docs_architecture_idempotent_settlement [EXTRACTED 1.00]
- **Validation scope and limits** — docs_validation_test_suite, docs_validation_mocked_sdk_validation, docs_validation_docker_limitations, docs_validation_untested_failover [EXTRACTED 1.00]
- **Versioned Evidence-backed Evaluation Pipeline** — docs_cqa_backend_immutable_checklists, docs_cqa_backend_durable_jobs, docs_cqa_backend_provider_evaluator, docs_cqa_backend_provider_critic, docs_cqa_backend_existing_scoring_adapter [EXTRACTED 1.00]

## Communities (62 total, 13 thin omitted)

### Community 0 - "Оценка диалогов CQA"
Cohesion: 0.07
Nodes (33): main(), CompatibleEvaluationRequest, compare(), main(), _records(), ProviderEvaluator, Analysis, EvaluationRequest (+25 more)

### Community 1 - "Схемы и API CQA"
Cohesion: 0.06
Nodes (24): BasicExtractor, Extractor, WorkspaceRequest, AppealView, EvaluationView, ReviewView, ReviewRequest, ChecklistCreate (+16 more)

### Community 2 - "Настройки и тесты API"
Cohesion: 0.07
Nodes (28): Settings, ProviderCritic, test_benchmark_counts_missing_as_wrong(), test_workspace_persistence_conflict_and_api_validation(), import_local(), test_invalid_organizer_responses_are_redacted(), test_organizer_uses_configured_url_verbatim_and_rejects_other_hosts(), handler() (+20 more)

### Community 3 - "Провайдеры языковых моделей"
Cohesion: 0.08
Nodes (20): GeneratedJSON, HTTPProvider, Provider, ProviderError, RedactHTTPLogs, request_json(), build_provider(), MockProvider (+12 more)

### Community 4 - "Расходы и ответы LLM"
Cohesion: 0.08
Nodes (16): ModelPrice, Settings, LLMResponse, RunSnapshot, Usage, console_summary(), PolicyEngine, cost_microdollars() (+8 more)

### Community 5 - "Проверки резервирования бюджета"
Cohesion: 0.15
Nodes (38): bind_run(), RunStatus, FakeProvider, configured(), test_parallel_settlements_and_reservations_preserve_invariant(), reserve(), test_atomic_five_reservations_one_dollar(), test_duplicate_reservation_never_increments() (+30 more)

### Community 6 - "Авторизация контекста запуска"
Cohesion: 0.10
Nodes (20): current_run(), RunContextSigner, AuthorizationError, BudgetExceededError, BudgetStoreUnavailableError, ConcurrencyLimitError, ConfigurationMismatchError, DuplicateCallError (+12 more)

### Community 7 - "Политики ограничений TokenOps"
Cohesion: 0.05
Nodes (40): max_tokens, max_usd, action, enabled, max_parallel_calls, queue_timeout_s, action, enabled (+32 more)

### Community 8 - "Демонстрации параллельного выполнения"
Cohesion: 0.11
Nodes (16): main(), AnalysisAgent, concurrent_scenario(), _concurrent_worker(), main(), ResearchAgent, run_demo(), single_process_scenario() (+8 more)

### Community 9 - "Публикация GitHub Pages"
Cohesion: 0.06
Nodes (34): runs-on, steps, concurrency, cancel-in-progress, group, environment, needs, runs-on (+26 more)

### Community 10 - "Апелляции и модели данных"
Cohesion: 0.14
Nodes (11): Appeal, Base, Evaluation, ReviewHistory, create_appeal(), final_result(), review_appeal(), validate_result() (+3 more)

### Community 11 - "Валидация настроек TokenOps"
Cohesion: 0.09
Nodes (16): BasicClassifier, Classifier, BudgetConfig, ConcurrencyCap, CostBudget, CostGuard, load_settings(), ObservabilityConfig (+8 more)

### Community 12 - "Хранилище бюджета Redis"
Cohesion: 0.15
Nodes (3): work(), RedisLedger, run()

### Community 13 - "Контейнеры Foundation backend"
Cohesion: 0.07
Nodes (28): build, environment, extra_hosts, ports, restart, volumes, context, dockerfile (+20 more)

### Community 14 - "Контейнеры Redis и демонстраций"
Cohesion: 0.07
Nodes (28): build, depends_on, environment, profiles, redis, REDIS_URL, TEST_REDIS_URL, interval (+20 more)

### Community 15 - "Чеклисты и совместимость"
Cohesion: 0.18
Nodes (21): ensure_checklist(), evaluation_view(), import_dialog(), install_compat(), evaluate(), get_workspace(), history(), put_workspace() (+13 more)

### Community 16 - "Очередь заданий оценки"
Cohesion: 0.17
Nodes (14): EvaluationJob, now(), create_job(), Pipeline, Worker, setup_job(), test_cache_covers_model_prompt_checklist_and_source(), test_failure_and_explicit_retry() (+6 more)

### Community 17 - "Тарифы моделей OpenAI"
Cohesion: 0.08
Nodes (23): cache_write_usd_per_million, cached_input_usd_per_million, input_billing_multiplier, input_usd_per_million, max_input_tokens, max_output_tokens, model_id, output_usd_per_million (+15 more)

### Community 18 - "Основной интерфейс React"
Cohesion: 0.14
Nodes (15): App(), AppealForm(), Avatar(), Badge(), Button(), CriterionForm(), DecisionForm(), icons (+7 more)

### Community 19 - "Зависимости и сборка frontend"
Cohesion: 0.12
Nodes (19): dependencies, @fontsource-variable/manrope@^5.3.0, lucide-react@^0.468.0, react@^19.0.0, react-dom@^19.0.0, devDependencies, @playwright/test@^1.65.0, prettier@^3.9.10 (+11 more)

### Community 20 - "Управляемые вызовы LLM"
Cohesion: 0.20
Nodes (6): RunContext, log_event(), CallPlan, GovernedLLMClient, cleanup(), test_store_down_blocks_dispatch()

### Community 21 - "Чеклисты и совместимость"
Cohesion: 0.18
Nodes (11): checklist_create(), evaluate(), load_dataset(), main(), Checklist, MessageView, create_checklist(), seed_checklist() (+3 more)

### Community 22 - "Маршруты и жизненный цикл"
Cohesion: 0.11
Nodes (12): create_app(), appeal_create(), appeal_review(), evaluation(), evaluation_job(), evaluations(), health(), lifespan() (+4 more)

### Community 23 - "Руководство по TokenOps"
Cohesion: 0.21
Nodes (15): Historical Token-saving Query, Historical Retrieval Context Estimate, Demonstrations A–E, Freedom CQA and TokenOps Guide, FakeProvider, GovernedLLMClient, Shared HALT and Billing Recovery, Validated Model Pricing (+7 more)

### Community 24 - "Импорт и экспорт workspace"
Cohesion: 0.16
Nodes (9): normalize_records(), read_workspace(), WorkspaceConflict, write_workspace(), record(), test_bad_inputs_fail_explicitly(), test_cli_import_and_export_are_durable(), test_cli_refuses_to_overwrite_browser_changes() (+1 more)

### Community 25 - "Архитектура резервирования бюджета"
Cohesion: 0.11
Nodes (9): Official OpenAI SDK and pricing references, PolicyEngine admission decisions, TokenOps architectural sources, Five-process shared-budget validation, Crash and transport-failure validation, Mocked AsyncOpenAI validation, 47 passing tests, Built wheel includes Lua (+1 more)

### Community 26 - "Контракты и интеграция Phase2"
Cohesion: 0.18
Nodes (17): Revisioned Appeal Review, CQA Backend Foundation Contract, Durable Evaluation Jobs, Exact Evidence Validation, ExistingScoringAdapter, Organizer Dataset Import, Pipeline Extension Contracts, ProviderCritic (+9 more)

### Community 27 - "Автоматические проверки Python"
Cohesion: 0.11
Nodes (18): REDIS_URL, TEST_REDIS_URL, jobs, pytest, name, on, runs-on, services (+10 more)

### Community 28 - "Тестовые тарифы моделей"
Cohesion: 0.11
Nodes (17): input_usd_per_million, max_input_tokens, max_output_tokens, model_id, output_usd_per_million, provider, source, models (+9 more)

### Community 29 - "Импорт наборов диалогов"
Cohesion: 0.23
Nodes (13): organizer(), datasets(), Conversation, Message, DatasetEnvelope, ImportResult, fetch_organizer(), import_dataset() (+5 more)

### Community 30 - "Документация приложения Phase2"
Cohesion: 0.13
Nodes (11): Immutable Original Evaluation, Configuration-sensitive Evaluation Cache, Local Deployment Boundary, Phase 2 Unified Application Guide, Phase 2: 148 Tests Passed, Phase 2 Verification Report, Private DEV Import Validation, Synthetic Ollama Live Validation (+3 more)

### Community 31 - "Расчёт оценок frontend"
Cohesion: 0.17
Nodes (9): conversations, initialCriteria, r(), raw, results(), scoreEvaluation(), base, perfect (+1 more)

### Community 32 - "Контейнер локальной Ollama"
Cohesion: 0.17
Nodes (11): NO_PROXY, OLLAMA_NUM_PARALLEL, SSL_CERT_FILE, environment, image, ports, volumes, services (+3 more)

### Community 33 - "Экран критериев оценки"
Cohesion: 0.20
Nodes (11): Freedom Broker checklist v1, Closing: 5 points, Criteria configuration and addition, Correct and complete consultation: 20 points, Contact establishment: 10 points, Dialogue management, speed and literacy: 15-point badge, Empathy and customer focus: 15 points, Gross errors: separate flag (+3 more)

### Community 34 - "Исходный экран анализа"
Cohesion: 0.20
Nodes (11): Per-criterion dispute actions, Two attention findings linked to message m7, Incomplete consultation: 10 of 20, CQA-1048 withdrawal dialogue, Checklist v1 evaluation with per-criterion evidence, No gross errors detected, Dialogue management: 7 of 10, Seven-criterion dialogue quality profile (+3 more)

### Community 35 - "Атомарные операции Lua"
Cohesion: 0.35
Nodes (7): event(), halt(), inc(), n(), running(), steer(), unknown()

### Community 36 - "Экран анализа диалога"
Cohesion: 0.22
Nodes (9): Criterion score appeal action, Checklist criteria with remarks and N/A filters, CQA-1048 withdrawal dialogue analysis, AI evaluation history, Criterion evidence linked to transcript message m7, Model health check: model not loaded, Ollama dialogue evaluation controls, Synthetic demonstration score: 81.88/100 (+1 more)

### Community 37 - "Мобильная очередь диалогов"
Cohesion: 0.20
Nodes (10): Dialogue import and export actions, Dialogue cards with client, operator, channel, language and score, Gross-error warning on dialogue CQA-1041, Demonstration dataset of 10 dialogues stored in browser, Evaluated dialogues with green scores, Dialogue search, language, channel and newest-first filters, Awaiting-evaluation dialogue without score, Under-review dialogues with amber scores (+2 more)

### Community 38 - "Документация интерфейса Freedom"
Cohesion: 0.20
Nodes (9): Dark Review Workspace UX Review, Freedom Broker HTML Entry, Freedom Broker Quality Intelligence, Historical Criteria Snapshot, Freedom Broker Frontend Guide, GitHub Pages Static Deployment, React Vite Review Interface, ReviewWorkspace (+1 more)

### Community 39 - "Мобильный контроль качества"
Cohesion: 0.22
Nodes (9): Demonstration data disclosure, Dialogue cards with scores and review statuses, AI evaluation history action, Mobile dialogue quality-control list, Ollama evaluation with model health and cache controls, Dialogue/customer search with language, channel and sort filters, Server storage connected indicator, All, under review, unscored and gross-error filters (+1 more)

### Community 40 - "Панель показателей качества"
Cohesion: 0.22
Nodes (9): Dashboard dialogue import and export actions, Quality breakdown by evaluation criterion, Browser-stored demonstration data, Dialogue search and language, channel, order filters, Quality KPIs: 9 analyzed, 92 average, 3 under review, 0 active appeals, Evaluation methodology tab, Recent dialogues table with operator, channel, language, score and status, Freedom Broker quality overview dashboard (+1 more)

### Community 41 - "Таблица диалогов Freedom"
Cohesion: 0.22
Nodes (9): Demonstration dataset and demo-data badges, Desktop dialogue quality-control table, Dialogue rows with operator, channel, score, status and time, Ollama model check, evaluation, cache bypass and history, Per-row open dialogue action, Customer/dialogue search, language/channel filters and sorting, All 10, under review 3, unscored 1 and gross errors 1, Dialogue upload and export actions (+1 more)

### Community 42 - "Просмотр доказательств оценки"
Cohesion: 0.42
Nodes (8): isIssue(), MarkedText(), number(), resultRatio(), ReviewWorkspace(), chooseFilter(), moveSearch(), showEvidence()

### Community 43 - "Контракты и интеграция Phase2"
Cohesion: 0.33
Nodes (5): Repository Agent Instructions, Stable Canonical Message IDs, Legacy Frontend Compatibility API, Phase 2 Integration Handoff, Three-person Team Workflow

### Community 45 - "Аудит перехода Foundation"
Cohesion: 0.40
Nodes (5): Phase 2 Baseline Audit, Baseline Separate Application Histories, Stale TokenOps-only Graph, Foundation Authoritative Store, SQLite Persistence

### Community 46 - "Экран подачи апелляции"
Cohesion: 0.40
Nodes (6): Score appeal modal, Appeal reason text field, Correct and complete consultation, Evaluation explanation and quoted dialogue evidence, Original score: 10, Submit appeal for review

### Community 47 - "Панель запуска оценки"
Cohesion: 0.60
Nodes (5): EvaluationPanel(), refreshHealth(), run(), showHistory(), readResponse()

### Community 48 - "Команды сборки frontend"
Cohesion: 0.40
Nodes (5): scripts, build, dev, preview, test:smoke

### Community 52 - "Логотип Freedom CQA"
Cohesion: 0.67
Nodes (3): Freedom CQA Mark, Green Rounded-square Background, White f Monogram and Dot

## Knowledge Gaps
- **71 isolated node(s):** `tokenops-guard`, `TokenOps architectural sources`, `Official OpenAI SDK and pricing references`, `Built wheel includes Lua`, `SQLite Persistence` (+66 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 424 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `OpenAIProvider` connect `Расходы и ответы LLM` to `Демонстрации параллельного выполнения`, `Авторизация контекста запуска`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `RedisLedger` (e.g. with `main()` and `concurrent_scenario()`) actually correct?**
  _`RedisLedger` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `tokenops-guard`, `TokenOps architectural sources`, `Official OpenAI SDK and pricing references` to the rest of the system?**
  _71 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Оценка диалогов CQA` be split into smaller, more focused modules?**
  _Cohesion score 0.06875 - nodes in this community are weakly interconnected._
- **Why does `RedisLedger` connect `Хранилище бюджета Redis` to `Расходы и ответы LLM`, `Проверки резервирования бюджета`, `Авторизация контекста запуска`, `Демонстрации параллельного выполнения`, `Управляемые вызовы LLM`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `create_app()` (e.g. with `lifespan()` and `Appeal`) actually correct?**
  _`create_app()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Should `Схемы и API CQA` be split into smaller, more focused modules?**
  _Cohesion score 0.06390977443609022 - nodes in this community are weakly interconnected._
## Ограничения и аудит выполнения

Проанализировано 119 файлов: 95 файлов кода, 15 документов и 9 изображений (47 222 слова). Все 22 некэшированных документа и изображения прочитаны полностью; ещё 2 документа взяты из кэша. Структурный экстрактор сообщил о 10 файлах без символов: файлы данных и неподдерживаемые конструкции ограничивают полноту связей вызовов.

Диагностика исходного извлечения: 339 связей с отсутствующими в извлечении узлами, 1 петля и 143 связи с совпадающими парами узлов в неориентированном графе. Эти ограничения экстрактора означают, что карта не является полным доказательством поведения программы. Подробности и примеры: graph_health.json. Целостность конечного graph.json проверяется отдельно: все его связи должны ссылаться на существующие узлы.

Измеренные input/output usage сессии недоступны; нули в локальном cost.json — технические placeholders. Дополнительные платные API семантического анализа не вызывались.

Benchmark на фактическом корпусе: 47222 слов / примерно 62962 токенов; средний запрос — примерно 1628 токенов; оценочное сокращение 38.7×. Это синтетическая оценка размера контекста четырёх запросов, а не измерение расхода сессии или качества ответов. CLI без corpus_words использует оценку по числу узлов и завышал базу до 58 850 слов; здесь использованы 47 222 слова из detect.

graphify-out/ записана в рабочее дерево и уже исключена через .gitignore. Для команды в Git добавлены только graph.html, graph.json, GRAPH_REPORT.md и graph_health.json; кэш, manifest и файлы окружения остаются локальными. См. https://docs.graphify.com/guides/team-workflows.

### Коэффициенты связности без округления

| Группа | Связность |
|---|---:|
| Оценка диалогов CQA | 0.06875 |
| Схемы и API CQA | 0.06390977443609022 |
| Настройки и тесты API | 0.06623376623376623 |
| Провайдеры языковых моделей | 0.07676767676767676 |
| Расходы и ответы LLM | 0.08345428156748912 |
| Проверки резервирования бюджета | 0.15450980392156863 |
| Авторизация контекста запуска | 0.10365853658536585 |
| Политики ограничений TokenOps | 0.04878048780487805 |
| Демонстрации параллельного выполнения | 0.1092436974789916 |
| Публикация GitHub Pages | 0.06050420168067227 |
| Апелляции и модели данных | 0.1408199643493761 |
| Валидация настроек TokenOps | 0.08522727272727272 |
| Хранилище бюджета Redis | 0.14717741935483872 |
| Контейнеры Foundation backend | 0.06896551724137931 |
| Контейнеры Redis и демонстраций | 0.07142857142857142 |
| Чеклисты и совместимость | 0.17663817663817663 |
| Очередь заданий оценки | 0.16615384615384615 |
| Тарифы моделей OpenAI | 0.08333333333333333 |
| Основной интерфейс React | 0.14130434782608695 |
| Зависимости и сборка frontend | 0.11857707509881422 |
| Управляемые вызовы LLM | 0.20346320346320346 |
| Чеклисты и совместимость | 0.18095238095238095 |
| Маршруты и жизненный цикл | 0.10952380952380952 |
| Руководство по TokenOps | 0.20526315789473684 |
| Импорт и экспорт workspace | 0.15789473684210525 |
| Архитектура резервирования бюджета | 0.1111111111111111 |
| Контракты и интеграция Phase2 | 0.18128654970760233 |
| Автоматические проверки Python | 0.10526315789473684 |
| Тестовые тарифы моделей | 0.1111111111111111 |
| Импорт наборов диалогов | 0.22875816993464052 |
| Документация приложения Phase2 | 0.13333333333333333 |
| Расчёт оценок frontend | 0.175 |
| Контейнер локальной Ollama | 0.16666666666666666 |
| Экран критериев оценки | 0.2 |
| Исходный экран анализа | 0.2 |
| Атомарные операции Lua | 0.34545454545454546 |
| Экран анализа диалога | 0.2222222222222222 |
| Мобильная очередь диалогов | 0.2 |
| Документация интерфейса Freedom | 0.2 |
| Мобильный контроль качества | 0.2222222222222222 |
| Панель показателей качества | 0.2222222222222222 |
| Таблица диалогов Freedom | 0.2222222222222222 |
| Просмотр доказательств оценки | 0.4166666666666667 |
| Контракты и интеграция Phase2 | 0.3333333333333333 |
| Инициализация базы данных | 0.3333333333333333 |
| Аудит перехода Foundation | 0.4 |
| Экран подачи апелляции | 0.4 |
| Панель запуска оценки | 0.6 |
| Команды сборки frontend | 0.4 |
| Адаптер детерминированного скоринга | 0.5 |
| Совместимый вход ASGI | 0.6666666666666666 |
| Проверка исходной Foundation | 0.6666666666666666 |
| Логотип Freedom CQA | 0.6666666666666666 |
| Синхронизация рабочего пространства | 1.0 |
| Модули агентов CQA | 1.0 |
| Модуль долговечного backend | 1.0 |
| Транзакционные сервисы приложения | 1.0 |
| Адаптеры инфраструктуры CQA | 1.0 |
| Модуль оркестрации оценки | 1.0 |
| Интеграционные тесты CQA | 1.0 |
| Метаданные пакета TokenOps | 1.0 |
| Модуль тестов проекта | 1.0 |

Проверки артефактов: JSON успешно разобран; все 1 177 ID уникальны; все 2 975 конечных связей и участники гиперсвязей ссылаются на существующие узлы; локальные пути источников существуют; все 62 группы названы. HTML содержит обе подсистемы CQA и TokenOps. CLI-поиск проверен по src/tokenops_guard/ledger/redis_ledger.py::RedisLedger; для одноимённых узлов требуется уточнение пути. Исходный код приложения не изменялся.
