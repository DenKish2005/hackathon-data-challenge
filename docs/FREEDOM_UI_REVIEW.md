# Freedom desktop UI review

## Final target and scope

The latest user-selected target is the dark Freedom style: near-black canvas, graphite surfaces, bright green primary actions and white typography with the existing Freedom shield mark. Oracle deployment was deferred by the user; publishing on Vercel is a later task.

The primary workflow is conversation selection → evaluation review → source evidence → criterion-specific appeal and human decision. Fresh Chromium captures cover1440×1000 and1280×900 desktop viewports. No mobile iteration or full WCAG certification is claimed.

## Findings addressed

1. For chat review, the evidence/appeal actions previously began at y1019 on1280×900. The chronology is now collapsed by default, the panels use the available viewport height and the explanation actions remain visible. Final action bounds are y796–857 at1280×900 and y896–957 at1440×1000.
The final telephone layout places the native player and real waveform side by side in a128px recording toolbar. With the waveform open and a ready evaluation, evidence/appeal actions are visible at y794–855 on1280×900 and y894–955 on1440×1000. Criterion results remain accessible in the independently scrolling quality panel.

2. Small pale modal text has been replaced with readable dark-theme typography. Criterion editing, import, appeal and decision forms use the same surface/action hierarchy.
3. Missing criterion results no longer show passed checks. An incomplete evaluation has no calculated total; an absent critical-error result is unknown. A known positive critical flag remains visible even if another criterion is missing.
4. Typing in transcript search preserves focus; Enter moves between matches, and clear resets the query. Evidence navigation still focuses the original source message.
5. The user-reported appeal failure was reproduced when `crypto.randomUUID` was unavailable on a non-secure HTTP host. The submission now uses a safe ID fallback and creates the appeal before the state updater. A repeated submit produces one appeal; the review remains responsive after reload.
6. Failed JavaScript loading produces visible recovery instructions instead of an empty document. Unavailable or corrupt local storage does not blank the workspace.

The last visual pass also fixed old light-theme text colors in overview table titles, chart tooltips and the selected overview tab. Their final computed foreground is readable light ink (`rgb(224,238,228)` for titles/tooltips). Pending imported calls now explicitly say “Оценка ещё не выполнена”, without a misleading demo-evaluation label.

## Verification

The production frontend build passes. All three browser suites pass against production preview4173:

- `tests/smoke.mjs`: eight criteria, score scales/N/A/critical flag, explicit selection, search/filtering, snapshot versions, source evidence, scoped export, contextual appeal/recalculation,100-message layout, pending import and deep links.
- `tests/evaluation.mjs`: visible503 error and valid result application, stale appeal protection, switching dialogues during evaluation, stale history, pending→ready and shared-workspace hydration/revision protections.
- `tests/reliability.mjs`: partial results/critical unknown state, known critical flag with an incomplete score, blocked/corrupt storage, sequential keyboard search, unavailable `randomUUID`, repeated appeal submit/reload/review, organizer voice-call import with loading protection, preserved ISO timestamps/audio metadata, real generated-WAV playback/seek and decoded-waveform keyboard navigation, recording reset when switching calls, no fake player without an audio URL, numeric-ID rejection, mocked evaluation/evidence, and blocked-JS recovery.

Organizer/model responses are mocked in browser contract tests. The telephone case verifies evaluation of the provided transcript and real native audio playback/seek using a generated PCM-WAV fixture served with HTTPS/CORS/byte-range behavior. The waveform is derived from decoded samples, and no speaker identities or separate speaker tracks are inferred. The phone screenshot uses a generated8-second WAV test fixture. This does not claim automatic speech recognition, audio playback against the real organizer endpoint, or measured model accuracy. Real Ground Truth accuracy requires a separate held-out benchmark. The source's signed organizer URL is absent from fixtures, screenshots and this report.

Across11 surfaces at both desktop widths, there is no horizontal page overflow and no uncaught JavaScript error in the captured workflow.

## Accepted screenshot set

- [Conversation selection](../frontend/docs/freedom-selection.png)
- [Selected-dialogue preview](../frontend/docs/freedom-desk-selected.png)
- [Transcript, score and evidence](../frontend/docs/freedom-dialogue.png)
- [Appeal form](../frontend/docs/freedom-appeal.png)
- [Appeal list](../frontend/docs/freedom-appeals.png)
- [Checklist](../frontend/docs/freedom-criteria.png)
- [Criterion editor](../frontend/docs/freedom-criterion-editor.png)
- [Dataset overview](../frontend/docs/freedom-overview.png)
- [Methodology](../frontend/docs/freedom-methodology.png)
- [Organizer import](../frontend/docs/freedom-import.png)
- [Pending telephone conversation, real player and decoded waveform](../frontend/docs/freedom-phone.png)

All screenshots were freshly captured from the production preview and visually inspected. They demonstrate prototype behavior with synthetic/mock records, not a successful public deployment or a live-model benchmark.

## Проверка интегрированной версии, 7 ноября 2026

Новый Foundation API объединён с интерфейсом. Проверен реальный MP3 организаторов
через same-origin endpoint: длительность393.22секунды, нативное воспроизведение,
перемотка и160точек формы волны из декодированного аудио. Исходная ссылка ведёт
на HTML-плеер; backend извлекает доверенный источник MP3. Приватные данные и
подписи не включены в отчёт или скриншоты. Если сервер отдаёт неполный фрагмент,
интерфейс не выдаёт его за полную звуковую дорожку.

Отдельный браузерный тест использует настоящие FastAPI/SQLite, синтетический
диалог и явно включённый mock-провайдер. Он проверяет импорт до оценки,
асинхронное задание, восемь критериев, апелляцию, сохранение и версионирование.
Контрактные тесты дополнены состояниями очереди, отказом задания, облачным
провайдером и обозначением предварительной оценки. Это проверки интеграции,
а не замер accuracy относительно Ground Truth.
