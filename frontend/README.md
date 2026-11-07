# Freedom Broker · Quality Intelligence

![Analytics for one selected dialogue](docs/freedom-dialogue.png)

[Conversation selection screen](docs/freedom-selection.png)

[Desktop selection workspace](docs/freedom-selection.png)

Responsive Russian-language frontend for the CQA hackathon. Built with React, Vite and Lucide icons. Changes in this PR are confined to `frontend/`.

## Run

Requires Node.js 20.19+ or 22.12+ (validated with Node 24).

```bash
cd frontend
npm ci
npm run dev
```

Production: `npm run build`. Serve `dist/` using your web server, or use `npm run preview` for local verification.

## Working features

- Dashboard, overview metrics, computed conversation and criterion charts.
- Conversation list with search, language, channel and status filters.
- Transcript next to per-criterion results; evidence links highlight the source message.
- Eight initial checklist criteria from the provided PDF, including scales, N/A and separate critical-error flag.
- Checklist editor and new criteria, with version increments. Existing results retain their original rules.
- Appeal submission and human review; score recalculation retains original answers and score.
- JSON import for the organizers' `data.records` response; imported conversations remain pending evaluation.
- JSON export of checklist, conversations and appeals.
- Responsive mobile navigation, accessible labelled forms, keyboard modal focus management.

## Demo boundaries

The UI starts with **synthetic demonstration conversations**, not the organizers' DEV dataset. Analytics charts are computed from the current demonstration evaluations. The application does not call an LLM, run agents, import automatically from a signed URL, or authenticate users. Agent cards explain planned roles. An imported conversation has no generated evaluation. No API keys or signed URLs belong in the frontend.

Browser-local state is saved in localStorage. This is convenient for a prototype, not shared server storage. Clear the site's browser storage to reset the demo. Store real conversations and decisions on your backend when connecting the product; review browser retention needs before importing confidential data.

## Backend integration contract

Coordinate any contract change with both the frontend and backend owners. Do not import Python model code into the frontend. The initial view models are in `src/data.js`:

- Conversation: `id`, `customer`, `agent`, `channel` (`chat`/`call`), `language` (`RU`/`KZ`/`EN`), `topic`, `date`, `duration`, `status`, `messages`, `results`, `score`, `critical`, optional `audio_url`.
- Message: `id`, `role` (`client`/`operator`/`bot`/`system`), `text`, original `time`.
- Criterion: `id`, `title`, `description`, `weight`, `type` (`binary`/`scale`/`flag`), `scale`, `naAllowed`, `naCondition`.
- CriterionResult: `criterionId`, `answer`, `reason`, `evidenceId`.
- Existing evaluations may carry `checklistVersion` and `criteriaSnapshot`; resolve appeals against that snapshot, not newly edited rules.

Connect a backend service through a dedicated client module in `frontend/src/`, replacing local persistence and fixture reads. Suggested endpoints: conversations, checklist versions, evaluation jobs/results, appeals and review decisions. Backend must preserve full immutable evaluation history, validate all edits and recalculate independently of the browser. For missing actions or N/A, extend the response contract with checked ranges and explicit applicability explanations. Calls need audio-relative timing before implementing seek-to-evidence; the current UI links to original audio if provided.

Scoring normalizes numeric scales, excludes allowed N/A weights, rounds the final result to two decimals and treats critical errors separately. Missing results return an incomplete score, not zero. The frontend calculator is for the prototype and should be verified against the backend implementation.

## Checks

```bash
npm run build
# Start npm run dev in another terminal first:
npm run test:smoke
```

The smoke test uses installed Chromium at `/usr/bin/chromium`. Set `CHROMIUM_PATH` and `BASE_URL` for other environments. It checks scoring, search/filters, evidence navigation, appeal review, checklist persistence, JSON import, modal keyboard dismissal and mobile overflow.

## Three-person Git workflow

| Owner                    | Files                                                                                    | Suggested branch    |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------- |
| Frontend                 | `frontend/**`                                                                            | `feat/cqa-frontend` |
| Backend / infrastructure | backend implementation and deployment configuration, excluding `frontend/**`             | `feat/cqa-backend`  |
| AI / evaluation          | evaluator, prompts, criteria configuration and quality fixtures, excluding `frontend/**` | `feat/cqa-ai`       |

Agree on exact backend/AI paths before creating them. The existing `src/tokenops_guard/` package is separate from this new frontend and is unchanged by this PR.

Each person uses their own checkout and branch. Avoid concurrent checkout of different branches inside one shared directory. Edit only your owned paths; coordinate shared API contracts, root README, CI and Compose files before changing them.

```bash
git fetch origin
git switch -c feat/your-task origin/main
# Implement and test your task.
git add path/to/your/files
git commit -m "Describe the implemented feature"
git push -u origin feat/your-task
# Open a PR into main and request a teammate's review.
```

Before merging, fetch main and merge it into your feature branch, resolve conflicts in your own files and rerun affected checks. Use one PR per coherent task. Do not force-push a shared branch. Merge PRs one at a time; cross-directory integration happens through the agreed API contract.

## Freedom design refresh

The UI uses a Freedom-inspired light green-and-white palette and a typographic Freedom Broker lockup. Roboto is self-hosted, including Cyrillic, so the interface does not depend on Google Fonts. Existing browser-local state migrates from the previous prototype's storage keys.

Charts and criterion summaries now derive from the current evaluations instead of fixed illustration values. The chart selector switches the latest seven evaluations/all evaluations, not an unsupported date filter. New checklist versions do not retroactively change historical results.

Production assets use relative paths, suitable for either a server root or a GitHub Pages repository subpath. Public deployment still needs an explicitly selected hosting target and access.

## Primary flow: choose one dialogue

The application starts at a desktop control desk based on the supplied sketch: checklist left, chat selection right, general statistics below, and a selected-dialogue preview. Select a conversation, then click **Открыть аналитику** for its full review. The per-dialogue screen shows its own score, operator, channel, critical flag, criterion profile and evidence-backed findings. It never substitutes the dataset average for the selected dialogue's score.

The dropdown switches the entire analysis to another conversation. `#dialog/<id>` links survive page reload and browser back/forward. A pending imported dialogue has no fabricated score or findings. The **Отчёт** action exports only the selected dialogue and its associated appeals; the list's export includes the dataset. Aggregate statistics remain a separate secondary section.

## GitHub Pages publishing

The repository workflow `.github/workflows/frontend-pages.yml` builds and publishes the frontend on pushes to `main` affecting the frontend, and supports manual runs. It uses official GitHub Pages actions and the workflow-provided token; no personal token or application secret is embedded.

A repository administrator must enable **Settings → Pages → Build and deployment → Source: GitHub Actions** once. If an earlier run failed because Pages was disabled, rerun **Publish Freedom CQA to GitHub Pages** after saving that setting. The expected project address is `https://denkish2005.github.io/hackathon-data-challenge/`; treat it as published only after the deployment job succeeds.

The production build uses relative asset paths, and hash routes work at a repository subpath. No server-side API or model is deployed by this workflow: it publishes the frontend prototype.

The supplied `https://fbroker.kz/statistics` reference could not be captured in this environment because outbound policy denied that destination. The flow and Freedom-inspired styling were verified on the local implementation, not against a captured copy of that page.

## Review workspace

The primary task remains **select a dialogue → verify its evaluation → inspect evidence → appeal when needed**. The UI uses one token-based stylesheet (`src/styles.css`) and a dedicated `ReviewWorkspace` component. Old decorative analytics and overlapping theme stylesheets were removed.

- Queue tabs expose all, review, pending and critical cases; search, language/channel filters, score sorting and ten-row pagination work together.
- Returning through “К списку диалогов” preserves the queue query. Ctrl/Cmd+K focuses search; previous/next controls follow the filtered queue.
- The desktop review is one compact score strip and two independently scrolling panes. One criterion expands at a time, with its reason, calculated contribution and a quote from the actual transcript.
- Transcript search marks matches and supports Enter/Shift+Enter navigation. Evidence links highlight and focus their source message.
- Mobile uses cards with visible score/status and separate evaluation/transcript tabs; evidence navigation switches panes automatically.
- Appeals and decisions include the original answer, explanation and source quote. The review history uses saved appeals rather than generated events.
- Agent implementation details are moved to a short methodology page; there are no simulated agent activity indicators or promotional panels.

See [UX review and verification](docs/ux-review.md). This is still a browser-local prototype with demonstration evaluations; the redesign does not introduce a live scoring model or shared persistence.

## Light desktop desk from supplied references

The latest design follows the user's notebook wireframe and Freedom presentation photo. Those supplied images are the visual source: a light workspace, checklist and conversation selector side by side, dataset statistics beneath them, and the selected dialogue's results and appeal entry points below. This iteration targets desktop, not a mobile layout.

`SelectionDesk.jsx` owns candidate selection and preview. No dialogue is preselected on a fresh visit; the analysis button is disabled until a selection is made. Selecting a row updates its preview without navigating away; the button opens the full transcript-and-criteria workspace. Pending dialogues have no invented score. Checklist edits create new versions while the selected historical evaluation retains its own rules.

The source site `https://fbroker.kz/` was retried but returned a policy403, so exact site colours/assets were not verified. The interpretation is grounded in the provided photos; the type uses self-hosted Roboto rather than claiming an official brand font. See `design-qa.md` for the desktop verification record.
