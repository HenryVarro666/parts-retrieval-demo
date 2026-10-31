# Three-language UI code review

Date: 2026-10-31
Base: `45fcf85`
Reviewed: uncommitted `web/app.js`, `web/i18n.js`, `web/index.html`, `web/style.css`, `partsid/web.py`, `tests/test_web.py`, and `tests/web_i18n.test.cjs`.

## Strengths

- The message catalog centralizes Chinese, English, and Spanish. Interpolation uses a replacement callback, preserving dollar signs and braces inside OCR values without evaluating markup (`web/i18n.js`, `t`).
- OCR text, VLM explanations, review content, filenames, identifiers, rankings, and numeric evidence remain source data. Rendering still uses `textContent` and DOM nodes (`web/app.js:360`, `web/app.js:493`).
- Language changes reuse the existing application state and render functions. The persistence layer catches blocked storage reads and writes, and the document language, title, metadata, image alternatives, and accessibility labels have explicit localization paths (`web/i18n.js`, `apply` and `setLanguage`).
- The static route adds only the allowlisted JavaScript asset; no inference or dataset code changed (`partsid/web.py:167`).

## Issues

### Critical

None found.

### Important

No open findings after the targeted recheck. The two initial findings below were fixed and verified.

1. **[P2, resolved] Match the actual shape-quality messages, including live-only outcomes.**

   Initial evidence: `web/i18n.js:406` and `web/i18n.js:407` registered paraphrases, while `I.localize` only matches exact strings. The backend emits `No sufficiently large foreground was separated from the background.` and `Foreground touches the image edge and may be clipped.` (`partsid/shape.py:63`, `partsid/shape.py:75`). Neither matched the initial catalog. The read/orientation failure, too-small-image, and degenerate-contour outcomes also lacked translations. `renderShape` passes these notes through `I.localize` (`web/app.js:464`), leaving English system-generated shape receipts in Chinese and Spanish.

   Initial reproduction: with language `es`, calling `I.localize` with each of those five backend strings returned the unchanged English string. Four other backend notes did translate. The saved dataset exercises the translated notes, so checking replay alone missed this.

   Resolution: the catalog now uses the exact backend foreground/edge sentences and includes read, small-image, and degenerate-contour messages. The new regression test passes. The consumer recheck extracts every `_unknown` sentence directly from `partsid/shape.py` and verifies Spanish localization for all eight failure notes, plus the successful heuristic note. No free-form evidence translation was introduced.

2. **[P2, resolved] Rerender upload mode when saved experiment data is unavailable.**

   Initial evidence: the language handler only called `renderAll` inside `if (state.data)`. Upload mode remains available after `/api/data` fails and can render independently through `setMode` and `readUpload`. A language switch therefore left dynamic metrics, OCR prompts, predict-button text, and live-result labels in the prior language. The initial `state.dataError` branch also applied the preset-record error placeholder to the live image panel.

   Initial reproduction: a Node VM harness evaluated the app with `/api/data` rejecting, entered live mode with an image selected, rendered once in Chinese, and dispatched the real language-change handler with `es`. The document language became `es`; `predict-label` remained `开始识别` and `ocr-text` remained `上传图片并开始识别`. The mode and image remained present.

   Resolution: the handler now rerenders whenever data exists or the active mode is live, and only applies saved-record error placeholders in preset mode (`web/app.js:696`). A new valid upload also clears the stored prior upload error (`web/app.js:658`). The consumer harness passes for empty, selected-image, loading, and completed-result live states with `state.data === null`, including upload-error relocalization and clearing.

### Minor

None identified that require separate action.

## Validation

- `node --test tests/web_i18n.test.cjs`: 6 passed after the fixes.
- `.venv/bin/python -m pytest tests/test_web.py -q`: 5 passed.
- Checked every literal `t(...)` reference and every HTML localization attribute against the catalog: no missing keys.
- Checked all 18 current catalog part IDs: translations are present.
- Evaluated the actual current app and catalog in a Node VM with a minimal DOM and controlled fetch/FileReader boundaries. Dispatched the real mode, file, language, and predict handlers. Verified live-state localization after saved-data failure; file/image preservation across switches; disabled controls and loading overlay during the same single predict request; localized result names, SQL receipts, gate reasons, and all deterministic shape notes; exact raw OCR/record preservation; error relocalization and clearing; and preset error fallback. This is a consumer-logic check, not a browser-layout or model-inference test.
- Inspected the HTML, CSS selector adjustments, static route, current saved system reasons, timing descriptions, and raw evidence render paths.
- Consulted the required graph tools first. The graph reported `empty_graph`, so source review was used; the graph's zero-risk response is not evidence of coverage.
- No model execution, package installation, shared-browser actions, or implementation edits were performed. Browser layout and real inference remain the executor's validation responsibility.

## Declined to judge

- Translation of raw OCR, VLM explanations, and model-assisted review prose: the requirements explicitly preserve their original content and generation language.
- Model accuracy, new benchmark results, and hardware performance: unchanged by this UI-localization scope; no model was run for this review.

## Assessment

**PASS.** Both initial P2 findings are fixed and the focused tests and consumer-state recheck pass. No open correctness, security, state-preservation, or localization finding remains within the reviewed scope. Browser layout and actual model execution are covered separately by the executor.
