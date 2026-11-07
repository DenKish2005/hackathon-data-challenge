# Freedom CQA — design and functional verification

The latest selected references are the user's dark Freedom Bank screenshots (bankffin.kz and loan-cash.freedombank.kz). They ground the near-black canvas, graphite panels, white wordmark and bright green actions. The workflow remains the user's CQA desk: choose one conversation, inspect its original transcript and criterion results, follow evidence, appeal and review. The existing Freedom shield is served locally; its source is documented in public/freedom-logo-source.md. No official brand font or live website capture is claimed.

## Delivered workflow

- Search, language/channel/status filters, critical cases and score sorting work on real current records. An explicit selection enables the analysis action.
- All versioned criteria remain available. Missing results are neutral and have no calculated score; missing critical data is never reported clear. Known critical errors remain visible in incomplete results.
- Choosing a criterion highlights its evidence. Transcript search retains typing focus; Enter/Shift+Enter navigates matches. ISO timestamps are shown compactly while original values remain in data and exports.
- A call's actual audio URL appears in an always-visible native player above the analysis. Optional waveform peaks come from decoded audio, with memory/size/time limits and keyboard seek. No artificial speaker tracks are generated. Expired links and CORS/decoding failures leave a truthful recovery state.
- Appeals work without crypto.randomUUID, deduplicate submit and retain their evaluation identity. An old appeal cannot mutate a newer evaluation. A real API/SQLite save and browser reload were checked separately from mocks.
- Blocked storage, invalid stored types and missing JS assets show recovery content rather than a blank page.

## Evidence and checks

See [full review](../docs/FREEDOM_UI_REVIEW.md) for current browser checks and screenshots. Production build, three browser suites, CQA tests, proxy tests and lint pass. Browser viewports are 1440×1000 and1280×900; no horizontal overflow or uncaught JS errors in verified flows.

Synthetic PCM-WAV files verify actual decoding/playback logic. Actual organizer audio playback is **not** claimed: the source domain is blocked in this execution environment. The uploaded private dataset was validated separately:65 records,60 chats,5 calls and5 audio links, all pending real evaluation. Neither those transcripts nor their signed URLs are published.

## Runtime and publication limits

The server provides optional multi-agent specialists and a final critic. Ground Truth accuracy has not been measured, and no real model was available in this environment. Vercel configuration and a protected API proxy are prepared; an authenticated deployment and reachable persistent/model backend are still required. Oracle work was paused by the user.
