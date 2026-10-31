# Chinese, English and Spanish UI verification

Date: 2026-10-31. Base: `45fcf85`. Scope: an immediate language switch in the existing local evidence workbench, including browser persistence, dynamic UI, errors, accessibility text and display names. Inference logic, source catalog and measured results are unchanged.

## Automated checks

- `uv run --frozen --extra experiments pytest -q`: **134 passed in 4.56 s**.
- `node --test tests/web_i18n.test.cjs`: **6 passed**. Covers default/normalized language, persistence, blocked storage, raw evidence interpolation, exact backend shape-note localization, and complete three-language catalogs with matching placeholders.
- The new `/i18n.js` allowlisted route was tested against a real HTTP server: initially 404 (RED), then passed after adding the route (GREEN).
- Exact backend shape-failure translations received a failing regression test before their fix, then passed.
- `node --check web/app.js`, `node --check web/i18n.js`, `git diff --check`, and reference checks for all HTML/static JavaScript translation keys: passed.
- All 11 original baseline SHA256 checksums match. No tracked file under `data/` or `results/` changed.
- [Independent review](2026-10-31-i18n-code-review.md): **PASS**. The reviewer also exercised the actual app consumer handlers in a VM with controlled I/O, including missing saved data, live loading/result state, one inference request across language changes, raw output preservation and error recovery. This is separate from the browser checks below.

## Actual in-app browser checks

Used the existing page at `http://127.0.0.1:8765/` and the real local Python service:

- Switched Chinese → English → Spanish → Chinese. Static controls, experiment names, part display names, SQL keyword/match receipts, shape status, gate decisions, timing scope and accessibility labels updated. Document title and `html.lang` updated; final language was restored to Chinese.
- Spanish remained selected after reload. Switching without reloading retained `sqlite_vlm` and `images/raw/2N3055/80876576.jpg`, the same scores, candidate IDs and raw OCR/model evidence.
- Spanish SQL-only replay for ATMEGA328P `133222141.jpg` correctly displayed a retrieval miss and **Empeora**, with the original correct baseline result.
- Selected a non-image file: the upload validation error displayed in English, then switched to Spanish. Selecting a valid image cleared it.
- Uploaded NE555 `20729665.jpg` and started real RapidOCR/SQLite/shape inference in Spanish. Switched to English while the request was running: filename and disabled/loading state were retained. The result was NE555 with the expected SQL alias receipt. Switching the completed result to Spanish preserved its service timing of **6.31 s** and its candidates; no second prediction was started by the language handler.
- A translation wrapper initially inherited the old status-dot/number styles, causing Spanish header overflow. After narrowing those CSS selectors, the default 670-pixel browser viewport had equal `clientWidth` and `scrollWidth` in English, Spanish and Chinese. No viewport override was used; other breakpoints were not separately exercised.
- Final browser warning/error log was empty. The local server remains available on port 8765.

Screenshots: [English](../screenshots/trilingual-en-2026-10-31.jpg), [Spanish](../screenshots/trilingual-es-2026-10-31.jpg).

## Continuation

The language resource is served by the existing Python server and runs directly in the browser. No build step, cloud translation call, model inference change or new Python dependency is required. Storage is optional: switching still works if browser storage is blocked, though that browser cannot retain the preference. Raw model/review prose deliberately keeps its generation language, as explained in the interface.
