# Ensemble and private-repository verification

Date: 2026-10-30, America/Chicago. Code commit tested: `5f3c76808820cc714db592b1c3476223d2a4fe83`.

The user authorized syncing the code, results and page to the existing private repository. GitHub metadata confirmed `HenryVarro666/parts-retrieval-demo` is private with default branch `main`; both `main` and `experiment/ocr-rerank-demo` were advanced by normal fast-forward pushes. The original app commit `f0252ce` was synced first, followed by the combination code/results. No force push or visibility change was used.

## Fixed-output combination results

All five policies cover the same 44 unique queries. Their definitions were recorded before running the replay, without fitting weights or per-example exceptions. Original labels, catalog and all five measured model output JSON files remain byte-for-byte unchanged.

| Policy | Top-1 | Wins / regressions vs new OCR views | VLM calls required |
|---|---|---|---|
| Five equal votes | 37/44 | 2 / 3 | 44 |
| One vote per family | 39/44 | 1 / 0 | 44 |
| RRF of OCR rankings and VLM singleton | 38/44 | 2 / 2 | 44 |
| Strong, unconflicted OCR first | 40/44 | 2 / 0 | 8 |
| OCR disagreement gate | 39/44 | 3 / 2 | 17 |

The strong-identifier rule restored `2N3055/80876576` and `ATMEGA328P/75189907` relative to RapidOCR views, with no regressions in this development set. The 40/44 result is an offline replay of actual previously generated outputs; there was no new VLM inference. The 8/44 count describes the rule's required calls, not a newly executed selective service. Timing estimates sum required complete branches and any called VLM generation, include candidate-generation work once, charge abstention calls, and exclude model loading. They are not measured end-to-end latency or proven deployment savings.

## Validation

- Eight new decision/alignment/cost tests were introduced before implementation. Full suite: **74 passed** locally and **74 passed** in a fresh remote clone.
- All 11 preserved baseline/catalog/label hashes match; the five measured source JSONs equal their `f0252ce` versions.
- The independent reviewer recomputed every decision, vote, call flag, stage sum, source hash and both-baseline paired metric. One RRF tie-rule metadata mismatch was corrected and replayed. No unresolved material finding remains; see `2026-10-30-ensemble-code-review.md`.
- JavaScript syntax and Git whitespace checks pass.
- In the actual browser, the strong gate displays 40/44, its estimated-time scope, and the branch evidence. The first 2N3055 sample takes the OCR-only branch and hides VLM evidence. The weak ATmega328P sample takes the VLM branch, displays both opinions, and changes to the correct catalog class. Browser warning/error logs were empty in the final check. Screenshot: `docs/screenshots/ensemble-workbench.jpg`.

## Fresh GitHub clone

A new `git clone --branch main --single-branch` fetched code commit `5f3c768`. In that untouched clone:

1. `python3 -m partsid.ensemble` reproduced all checked-in combination outputs byte-for-byte; `git status --porcelain` remained empty.
2. `uv sync --frozen --extra experiments` succeeded in a new environment.
3. `uv run --frozen --extra experiments pytest -q` passed all 74 tests; `node --check web/app.js` passed.
4. An ephemeral local server successfully returned the HTML, JavaScript, CSS, a dataset JPEG and `/api/data` with 44 samples / 10 runs / strong gate 40 correct and 8 required VLM calls. The test server was stopped afterward; the user's original local demo remains available on port 8765.
5. GitHub's connected API read back `main/results/ensembles/comparison.md` with the expected metrics, and repository metadata still reported private visibility.

The final documentation-only sync records this verification; it does not change the tested code or results. The clone was tested on the current Mac, not on another physical machine. Standard-Python replay does not need model dependencies or a GPU; actual MLX VLM re-inference remains Apple Silicon-specific. README documents the clone, locked installation, local page, OCR experiments and replay commands. Model caches and virtual environments remain excluded from Git.
