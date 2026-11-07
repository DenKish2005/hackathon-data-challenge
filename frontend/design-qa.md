# Design QA — Freedom presentation workspace

Final result: passed for the verified desktop flows.

## Reference and scope

The selected reference is the user's photographed Freedom quality-control presentation (`photo_1_2026-11-07_15-23-13.jpg`). The review follows its green CQA rail, white surfaces, Freedom mark at the top right, conversation timeline, transcript on the left and score/checklist on the right. The notebook sketch remains the reference for the selection desk.

This is a desktop interpretation of the supplied photographs, not a pixel clone of a tilted slide. Live access to `https://fbroker.kz/` was denied by network policy; no claim is made that the live website or official brandbook was captured. The existing Freedom shield is locally stored, with source documented in `public/freedom-logo-source.md`. Roboto is self-hosted, not asserted to be the official brand font.

## Implementation checks

- A fresh visit requires explicit conversation selection before opening analytics.
- The selected conversation has its own score, all eight historical criteria, actual transcript and evidence. A changed current checklist does not rewrite its snapshot.
- The ring sits beside the criterion list, matching the presentation hierarchy. Selecting a criterion shows one explanation below it, followed by its real quote and appeal action.
- The timeline shows actual message positions and timestamps. No fabricated sound waveform is shown; audio appears only when an actual audio URL exists.
- Evidence navigation highlights and focuses the referenced message and scrolls the transcript container. Amber highlights evidence and issues; primary reading text uses neutral dark ink.
- Pending dialogues retain an empty score and no invented findings. N/A normalization and separate critical flags remain unchanged.
- Advanced evaluation/history controls remain connected below the review. The teammate's Ollama evaluation and shared-workspace integration are retained.
- Import, export, contextual appeals, human review and score recalculation remain functional.

## Browser checks

Chromium: 1440×1000 and 1280×900 desktop viewports. No horizontal page overflow or JavaScript errors in the smoke flow. Build, desktop smoke and mocked frontend/backend evaluation contract pass. The contract verifies a visible503 failure followed by a successful response, the transcript, eight current criteria and cache flag sent to the backend. This does not establish real-model accuracy.

No mobile iteration was requested. Static GitHub Pages serves the UI; a separately running API is needed for model evaluation and shared persistence.

## Screenshots

- [Choose a conversation](docs/freedom-selection.png)
- [Selected conversation preview](docs/freedom-desk-selected.png)
- [Conversation analysis](docs/freedom-dialogue.png)
- [Contextual appeal](docs/freedom-appeal.png)
- [Checklist](docs/freedom-criteria.png)
- [Overview](docs/freedom-overview.png)
