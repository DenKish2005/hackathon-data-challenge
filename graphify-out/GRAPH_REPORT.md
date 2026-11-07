# Graph Report - Hackathon  (2026-11-07)

## Corpus Check
- 137 files · ~55,646 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 6, .example 1, .csv 1)

## Summary
- 1293 nodes · 3219 edges · 74 communities (56 shown, 18 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 560 edges (avg confidence: 0.91)
- Token cost: unavailable — collaboration tools do not expose actual host-agent usage; zero counters are placeholders, not a claim of free extraction.

## Community Hubs (Navigation)
- Расходы и ответы LLM
- Провайдеры языковых моделей
- Проверки резервирования бюджета
- Оценка диалогов CQA
- Настройки и тесты API
- Чеклисты и совместимость
- Политики ограничений TokenOps
- Схемы и API CQA
- Авторизация контекста запуска
- Контейнеры Foundation backend
- Публикация GitHub Pages
- Очередь и версии чеклистов
- Хранилище бюджета Redis
- Демонстрации параллельного выполнения
- Контейнеры Redis и демонстраций
- Конвейер и контракты оценки
- Документация и риски Phase3
- Тарифы моделей OpenAI
- Основной интерфейс React
- Маршруты и жизненный цикл
- Проверка браузера Playwright
- Руководство по TokenOps
- Архитектура резервирования бюджета
- Контракты и интеграция Phase2
- Автоматические проверки Python
- Управляемые вызовы LLM
- Тестовые тарифы моделей
- Зависимости и сборка frontend
- Очередь и метрики заданий
- Документация приложения Phase2
- Импорт и экспорт workspace
- Отчёты пакетной обработки
- Импорт и модели диалогов
- Команды импорта и оценки
- Инициализация базы данных
- Контейнер локальной Ollama
- Зависимости и сборка frontend
- Расчёт оценок frontend
- Оценка диалогов CQA
- Экран критериев оценки
- Исходный экран анализа
- Просмотр доказательств оценки
- Атомарные операции Lua
- Совместимые команды CLI
- Модель настроек backend
- Экран анализа диалога
- Мобильная очередь диалогов
- Документация интерфейса Freedom
- Мобильный контроль качества
- Панель показателей качества
- Таблица диалогов Freedom
- Измерение производительности Ollama
- Снимок реальной оценки
- Контракты и интеграция Phase2
- Аудит перехода Foundation
- Диагностика локального запуска
- Экран подачи апелляции
- Панель запуска оценки
- Адаптер детерминированного скоринга
- Валидация настроек TokenOps
- Проверка исходной Foundation
- Логотип Freedom CQA
- Метаданные пакета TokenOps

## God Nodes (most connected - your core abstractions)
1. `RedisLedger` - 61 edges
2. `create_app()` - 57 edges
3. `GovernedLLMClient` - 48 edges
4. `Usage` - 34 edges
5. `RunContext` - 31 edges

## Surprising Connections (you probably didn't know these)
- `test_workspace_persistence_conflict_and_api_validation()` --uses--> `Settings`  [INFERRED]
  tests/cqa/test_api.py → src/cqa/backend/config.py
- `test_new_group_uses_separate_private_full_url()` --uses--> `Settings`  [INFERRED]
  tests/cqa/test_phase3_batch.py → src/cqa/backend/config.py
- `Shared HALT and Billing Recovery` --conceptually_related_to--> `Single-process SQLite Worker`  [INFERRED]
  README.md → docs/cqa-backend.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Versioned Evidence-backed Evaluation Pipeline** — docs_cqa_backend_immutable_checklists, docs_cqa_backend_durable_jobs, docs_cqa_backend_provider_evaluator, docs_cqa_backend_provider_critic, docs_cqa_backend_existing_scoring_adapter [EXTRACTED 1.00]
- **Shared run enforcement flow** — readme_runcontext, readme_governedllmclient, readme_redisledger, docs_architecture_atomic_reservations, docs_architecture_idempotent_settlement [EXTRACTED 1.00]
- **Uncertain billing recovery flow** — docs_architecture_leases_heartbeat, docs_architecture_unknown_billing, readme_halt, readme_operator_recovery, docs_architecture_idempotent_settlement [EXTRACTED 1.00]
- **Validation scope and limits** — docs_validation_test_suite, docs_validation_mocked_sdk_validation, docs_validation_docker_limitations, docs_validation_untested_failover [EXTRACTED 1.00]
- **Durable evaluation and recovery across CLI, UI and restart tests** — docs_cqa_phase3_deployment_recoverable_batch_cli, docs_cqa_phase3_handoff_durable_ui_polling, docs_cqa_phase3_verification_recovery_tests, docs_cqa_phase3_verification_mock_batch_65 [INFERRED 0.85]
- **Privacy-preserving attempt telemetry from storage to measured calls** — docs_cqa_phase3_baseline_cqa_job_metrics, docs_cqa_phase3_handoff_attempt_metrics_contract, docs_cqa_phase3_performance_qwen3_benchmark [INFERRED 0.95]

## Communities (74 total, 18 thin omitted)

### Community 0 - "Расходы и ответы LLM"
Cohesion: 0.06
Nodes (31): main(), BudgetConfig, ConcurrencyCap, CostBudget, CostGuard, load_settings(), ModelPrice, ObservabilityConfig (+23 more)

### Community 1 - "Провайдеры языковых моделей"
Cohesion: 0.07
Nodes (23): GeneratedJSON, HTTPProvider, Provider, ProviderError, RedactHTTPLogs, request_json(), build_provider(), MockProvider (+15 more)

### Community 2 - "Проверки резервирования бюджета"
Cohesion: 0.16
Nodes (40): bind_run(), RunStatus, FakeProvider, GovernedLLMClient, configured(), ledger(), reserve(), test_atomic_five_reservations_one_dollar() (+32 more)

### Community 3 - "Оценка диалогов CQA"
Cohesion: 0.08
Nodes (29): CompatibleEvaluationRequest, ProviderEvaluator, Analysis, Criterion, EvaluationRequest, Evaluator, Finding, Message (+21 more)

### Community 4 - "Настройки и тесты API"
Cohesion: 0.08
Nodes (26): Settings, ProviderCritic, import_local(), test_invalid_organizer_responses_are_redacted(), test_organizer_uses_configured_url_verbatim_and_rejects_other_hosts(), handler(), test_real_worker_appeals_and_restart_persistence(), test_rest_crud_contracts_versions_cors_and_redacted_validation() (+18 more)

### Community 5 - "Чеклисты и совместимость"
Cohesion: 0.15
Nodes (32): ensure_checklist(), evaluation_view(), import_dialog(), install_compat(), evaluate(), get_workspace(), history(), put_workspace() (+24 more)

### Community 6 - "Политики ограничений TokenOps"
Cohesion: 0.05
Nodes (40): max_tokens, max_usd, action, enabled, max_parallel_calls, queue_timeout_s, action, enabled (+32 more)

### Community 7 - "Схемы и API CQA"
Cohesion: 0.08
Nodes (15): BasicClassifier, WorkspaceRequest, AppealView, EvaluationView, ReviewView, AppealCreate, ReviewRequest, ConversationView (+7 more)

### Community 8 - "Авторизация контекста запуска"
Cohesion: 0.11
Nodes (20): current_run(), RunContextSigner, AuthorizationError, BudgetExceededError, BudgetStoreUnavailableError, ConcurrencyLimitError, ConfigurationMismatchError, DuplicateCallError (+12 more)

### Community 9 - "Контейнеры Foundation backend"
Cohesion: 0.06
Nodes (34): build, environment, extra_hosts, healthcheck, ports, restart, volumes, context (+26 more)

### Community 10 - "Публикация GitHub Pages"
Cohesion: 0.06
Nodes (34): runs-on, steps, concurrency, cancel-in-progress, group, environment, needs, runs-on (+26 more)

### Community 11 - "Очередь и версии чеклистов"
Cohesion: 0.15
Nodes (20): Checklist, EvaluationJob, ChecklistCreate, create_checklist(), seed_checklist(), create_job(), Pipeline, default_checklist() (+12 more)

### Community 12 - "Хранилище бюджета Redis"
Cohesion: 0.15
Nodes (3): work(), RedisLedger, run()

### Community 13 - "Демонстрации параллельного выполнения"
Cohesion: 0.13
Nodes (15): AnalysisAgent, concurrent_scenario(), _concurrent_worker(), main(), ResearchAgent, run_demo(), single_process_scenario(), SummaryAgent (+7 more)

### Community 14 - "Контейнеры Redis и демонстраций"
Cohesion: 0.07
Nodes (28): build, depends_on, environment, profiles, redis, REDIS_URL, TEST_REDIS_URL, interval (+20 more)

### Community 15 - "Конвейер и контракты оценки"
Cohesion: 0.12
Nodes (9): BasicExtractor, Extractor, ChecklistView, ConversationDetail, Critic, EvaluationResult, Evaluator, MockEvaluator (+1 more)

### Community 16 - "Документация и риски Phase3"
Cohesion: 0.09
Nodes (20): cqa_job_metrics attempt telemetry, Phase 3 baseline — 2026-11-07, Initial verification at revision 58f249c, Docker Compose persistent deployment, Phase 3: локальный запуск и демонстрация, Local Ollama, FastAPI/React and persistent SQLite demo, FREEDOM_DATASET_URLS_FILE organizer URL map, Evaluation job metrics[] and calls[] contract (+12 more)

### Community 17 - "Тарифы моделей OpenAI"
Cohesion: 0.08
Nodes (23): cache_write_usd_per_million, cached_input_usd_per_million, input_billing_multiplier, input_usd_per_million, max_input_tokens, max_output_tokens, model_id, output_usd_per_million (+15 more)

### Community 18 - "Основной интерфейс React"
Cohesion: 0.14
Nodes (15): App(), AppealForm(), Avatar(), Badge(), Button(), CriterionForm(), DecisionForm(), icons (+7 more)

### Community 19 - "Маршруты и жизненный цикл"
Cohesion: 0.10
Nodes (15): create_app(), appeal_create(), appeal_review(), checklist_create(), conversation(), evaluation(), evaluation_job(), evaluations() (+7 more)

### Community 20 - "Проверка браузера Playwright"
Cohesion: 0.10
Nodes (9): api(), { chromium }, directory, env, report, require, root, socket (+1 more)

### Community 21 - "Руководство по TokenOps"
Cohesion: 0.21
Nodes (15): Historical Token-saving Query, Historical Retrieval Context Estimate, Demonstrations A–E, Freedom CQA and TokenOps Guide, FakeProvider, GovernedLLMClient, Shared HALT and Billing Recovery, Validated Model Pricing (+7 more)

### Community 22 - "Архитектура резервирования бюджета"
Cohesion: 0.11
Nodes (9): Official OpenAI SDK and pricing references, PolicyEngine admission decisions, TokenOps architectural sources, Five-process shared-budget validation, Crash and transport-failure validation, Mocked AsyncOpenAI validation, 47 passing tests, Built wheel includes Lua (+1 more)

### Community 23 - "Контракты и интеграция Phase2"
Cohesion: 0.18
Nodes (17): Revisioned Appeal Review, CQA Backend Foundation Contract, Durable Evaluation Jobs, Exact Evidence Validation, ExistingScoringAdapter, Organizer Dataset Import, Pipeline Extension Contracts, ProviderCritic (+9 more)

### Community 24 - "Автоматические проверки Python"
Cohesion: 0.11
Nodes (18): REDIS_URL, TEST_REDIS_URL, jobs, pytest, name, on, runs-on, services (+10 more)

### Community 25 - "Управляемые вызовы LLM"
Cohesion: 0.18
Nodes (4): RunContext, log_event(), CallPlan, cleanup()

### Community 26 - "Тестовые тарифы моделей"
Cohesion: 0.11
Nodes (17): input_usd_per_million, max_input_tokens, max_output_tokens, model_id, output_usd_per_million, provider, source, models (+9 more)

### Community 27 - "Зависимости и сборка frontend"
Cohesion: 0.13
Nodes (16): devDependencies, @playwright/test@^1.65.0, prettier@^3.9.10, vite@^6.0.0, name, private, scripts, build (+8 more)

### Community 28 - "Очередь и метрики заданий"
Cohesion: 0.21
Nodes (5): JobMetrics, now(), job_key(), Worker, test_recovery_does_not_duplicate_or_lose_jobs()

### Community 29 - "Документация приложения Phase2"
Cohesion: 0.13
Nodes (11): Immutable Original Evaluation, Configuration-sensitive Evaluation Cache, Local Deployment Boundary, Phase 2 Unified Application Guide, Phase 2: 148 Tests Passed, Phase 2 Verification Report, Private DEV Import Validation, Synthetic Ollama Live Validation (+3 more)

### Community 30 - "Импорт и экспорт workspace"
Cohesion: 0.23
Nodes (9): normalize_records(), read_workspace(), WorkspaceConflict, write_workspace(), record(), test_bad_inputs_fail_explicitly(), test_cli_import_and_export_are_durable(), test_cli_refuses_to_overwrite_browser_changes() (+1 more)

### Community 31 - "Отчёты пакетной обработки"
Cohesion: 0.17
Nodes (7): save_report(), summarize(), test_batch_report_resume_and_failed_only(), handler(), test_interrupt_writes_report_and_keeps_durable_job_id(), test_new_group_uses_separate_private_full_url(), test_unknown_tokens_and_cache_do_not_invent_throughput()

### Community 32 - "Импорт и модели диалогов"
Cohesion: 0.30
Nodes (8): Conversation, Message, DatasetEnvelope, ImportResult, import_dataset(), message_id(), test_import_preserves_records_and_is_atomic_idempotent(), test_real_dev_file_when_supplied()

### Community 33 - "Команды импорта и оценки"
Cohesion: 0.20
Nodes (10): organizer(), datasets(), evaluate(), fill(), run_one(), load_dataset(), main(), fetch_organizer() (+2 more)

### Community 35 - "Контейнер локальной Ollama"
Cohesion: 0.17
Nodes (11): NO_PROXY, OLLAMA_NUM_PARALLEL, SSL_CERT_FILE, environment, image, ports, volumes, services (+3 more)

### Community 36 - "Зависимости и сборка frontend"
Cohesion: 0.21
Nodes (9): dependencies, @fontsource-variable/manrope@^5.3.0, react@^19.0.0, react-dom@^19.0.0, serialize(), WorkspaceSync(), @fontsource-variable/manrope, react (+1 more)

### Community 37 - "Расчёт оценок frontend"
Cohesion: 0.24
Nodes (8): conversations, initialCriteria, r(), raw, results(), scoreEvaluation(), base, perfect

### Community 38 - "Оценка диалогов CQA"
Cohesion: 0.27
Nodes (5): main(), compare(), main(), _records(), test_benchmark_reports_coverage_and_rejects_duplicate_truth()

### Community 39 - "Экран критериев оценки"
Cohesion: 0.20
Nodes (11): Freedom Broker checklist v1, Closing: 5 points, Criteria configuration and addition, Correct and complete consultation: 20 points, Contact establishment: 10 points, Dialogue management, speed and literacy: 15-point badge, Empathy and customer focus: 15 points, Gross errors: separate flag (+3 more)

### Community 40 - "Исходный экран анализа"
Cohesion: 0.20
Nodes (11): Per-criterion dispute actions, Two attention findings linked to message m7, Incomplete consultation: 10 of 20, CQA-1048 withdrawal dialogue, Checklist v1 evaluation with per-criterion evidence, No gross errors detected, Dialogue management: 7 of 10, Seven-criterion dialogue quality profile (+3 more)

### Community 41 - "Просмотр доказательств оценки"
Cohesion: 0.31
Nodes (10): lucide-react@^0.468.0, isIssue(), MarkedText(), number(), resultRatio(), ReviewWorkspace(), chooseFilter(), moveSearch() (+2 more)

### Community 42 - "Атомарные операции Lua"
Cohesion: 0.35
Nodes (7): event(), halt(), inc(), n(), running(), steer(), unknown()

### Community 44 - "Модель настроек backend"
Cohesion: 0.22
Nodes (3): organizer_urls(), test_benchmark_counts_missing_as_wrong(), test_workspace_persistence_conflict_and_api_validation()

### Community 45 - "Экран анализа диалога"
Cohesion: 0.22
Nodes (9): Criterion score appeal action, Checklist criteria with remarks and N/A filters, CQA-1048 withdrawal dialogue analysis, AI evaluation history, Criterion evidence linked to transcript message m7, Model health check: model not loaded, Ollama dialogue evaluation controls, Synthetic demonstration score: 81.88/100 (+1 more)

### Community 46 - "Мобильная очередь диалогов"
Cohesion: 0.20
Nodes (10): Dialogue import and export actions, Dialogue cards with client, operator, channel, language and score, Gross-error warning on dialogue CQA-1041, Demonstration dataset of 10 dialogues stored in browser, Evaluated dialogues with green scores, Dialogue search, language, channel and newest-first filters, Awaiting-evaluation dialogue without score, Under-review dialogues with amber scores (+2 more)

### Community 47 - "Документация интерфейса Freedom"
Cohesion: 0.20
Nodes (9): Dark Review Workspace UX Review, Freedom Broker HTML Entry, Freedom Broker Quality Intelligence, Historical Criteria Snapshot, Freedom Broker Frontend Guide, GitHub Pages Static Deployment, React Vite Review Interface, ReviewWorkspace (+1 more)

### Community 48 - "Мобильный контроль качества"
Cohesion: 0.22
Nodes (9): Demonstration data disclosure, Dialogue cards with scores and review statuses, AI evaluation history action, Mobile dialogue quality-control list, Ollama evaluation with model health and cache controls, Dialogue/customer search with language, channel and sort filters, Server storage connected indicator, All, under review, unscored and gross-error filters (+1 more)

### Community 49 - "Панель показателей качества"
Cohesion: 0.22
Nodes (9): Dashboard dialogue import and export actions, Quality breakdown by evaluation criterion, Browser-stored demonstration data, Dialogue search and language, channel, order filters, Quality KPIs: 9 analyzed, 92 average, 3 under review, 0 active appeals, Evaluation methodology tab, Recent dialogues table with operator, channel, language, score and status, Freedom Broker quality overview dashboard (+1 more)

### Community 50 - "Таблица диалогов Freedom"
Cohesion: 0.22
Nodes (9): Demonstration dataset and demo-data badges, Desktop dialogue quality-control table, Dialogue rows with operator, channel, score, status and time, Ollama model check, evaluation, cache bypass and history, Per-row open dialogue action, Customer/dialogue search, language/channel filters and sorting, All 10, under review 3, unscored 1 and gross errors 1, Dialogue upload and export actions (+1 more)

### Community 52 - "Снимок реальной оценки"
Cohesion: 0.32
Nodes (8): Evaluation criteria panel shows eight total items and two remarks; expanded contact-establishment smoke v2 criterion receives 10/10 and quotes operator message m1, Visible demo-data badge, demonstration-mode account label and footer stating demo evaluation without running the model, Imported dialog browser-synthetic, client, Russian language, Ollama evaluation panel with model check, cache bypass, evaluation and history controls; completion label reports 1/1 successful, Evaluation description advertises two passes, verifiable quotations and server calculation; result metadata displays qwen3:4b, one pass and 4337 tokens, Displayed overall score 65/100, operator role, checklist version 2, seven applicable criteria, zero N/A and no serious errors, Freedom Broker imported-dialog analytics screenshot, Three-message transcript: operator Anna introduces Freedom Broker, client says the issue is resolved, operator closes the conversation

### Community 53 - "Контракты и интеграция Phase2"
Cohesion: 0.33
Nodes (5): Repository Agent Instructions, Stable Canonical Message IDs, Legacy Frontend Compatibility API, Phase 2 Integration Handoff, Three-person Team Workflow

### Community 54 - "Аудит перехода Foundation"
Cohesion: 0.40
Nodes (5): Phase 2 Baseline Audit, Baseline Separate Application Histories, Stale TokenOps-only Graph, Foundation Authoritative Store, SQLite Persistence

### Community 55 - "Диагностика локального запуска"
Cohesion: 0.47
Nodes (3): monitor(), doctor(), resources()

### Community 56 - "Экран подачи апелляции"
Cohesion: 0.40
Nodes (6): Score appeal modal, Appeal reason text field, Correct and complete consultation, Evaluation explanation and quoted dialogue evidence, Original score: 10, Submit appeal for review

### Community 57 - "Панель запуска оценки"
Cohesion: 0.60
Nodes (5): EvaluationPanel(), refreshHealth(), run(), showHistory(), readResponse()

### Community 62 - "Логотип Freedom CQA"
Cohesion: 0.67
Nodes (3): Freedom CQA Mark, Green Rounded-square Background, White f Monogram and Dot

## Knowledge Gaps
- **78 isolated node(s):** `tokenops-guard`, `SQLite Persistence`, `HTTP Batch Evaluation`, `TokenOps architectural sources`, `Official OpenAI SDK and pricing references` (+73 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 469 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `Маршруты и жизненный цикл` to `Импорт и модели диалогов`, `Команды импорта и оценки`, `Инициализация базы данных`, `Провайдеры языковых моделей`, `Настройки и тесты API`, `Чеклисты и совместимость`, `Оценка диалогов CQA`, `Схемы и API CQA`, `Очередь и версии чеклистов`, `Конвейер и контракты оценки`, `Очередь и метрики заданий`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `RedisLedger` (e.g. with `main()` and `concurrent_scenario()`) actually correct?**
  _`RedisLedger` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `tokenops-guard`, `SQLite Persistence`, `HTTP Batch Evaluation` to the rest of the system?**
  _78 weakly-connected nodes found - possible documentation gaps or missing edges._
## Extraction Health and Limits

GRAPH HEALTH WARNING: 401 raw edges reference missing nodes; 2 self-loops; 151 same-endpoint edges can collapse in the simple undirected graph. See `graph_health.json`. These diagnostics describe raw extraction before graph construction, not verified runtime dependencies.

All five new Phase 3 text files were read completely; the new screenshot was inspected visually. 24 unchanged documents/images were served from semantic cache. Screenshot labels are observations about the image, not proof of model execution or database persistence.

Structural extraction reported 11 code files with no extracted symbols (some still have file-level nodes). Data JSON files are not semantically interpreted as documents. Nine unsupported files were unclassified: Dockerfiles, ignore files, LICENSE, CSS and benchmark CSV; their mentions in documentation are not direct extraction coverage. Private `.runtime/`, virtual environments, build outputs and dependency directories were excluded. No sensitive-file exclusions were reported.

`graphify-out/` was written into the Git working tree. It is already ignored; selected deliverable files are tracked explicitly, while caches and machine-specific interpreter paths remain local.

## Retrieval Context Estimate

Detected corpus: 55,646 words, approximately 74,194 tokens; average matched-query context: 1,635 estimated tokens, ratio 45.4x. Four synthetic matching questions were measured. These are retrieval-size estimates, not billing, accuracy or measured end-to-end task savings. The CLI default estimates corpus size as node_count * 50; this result uses actual detect() words instead. See `benchmark.json`.

## Artifact Verification

JSON parsed successfully: 1,293 unique node IDs, 3,219 links whose endpoints all exist, and 74 communities. Phase 3 documents and screenshot are included. A real headless Chrome run opened graph.html as a local file, observed the matching node/edge counts and one canvas, and recorded no page errors. HTML needs no local web server; its vis-network library is loaded from a CDN, so the verified run had network access. `git diff --check` passed.
