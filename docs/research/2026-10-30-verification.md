# Implementation verification, 2026-10-30

## Measured results

All five experiment files in `results/experiments/` are complete and contain 44 unique queries. Recomputed summaries agree with saved records:

| Pipeline | Top-1 | Top-3 | Changes versus original baseline |
|---|---|---|---|
| EasyOCR whole | 27/44 | 33/44 | Original per-query rank outcomes reproduced in all five original channels |
| EasyOCR views | 29/44 | 33/44 | 6 wins, 4 regressions |
| RapidOCR / PP-OCRv6 small whole | 35/44 | 40/44 | 10 wins, 2 regressions |
| RapidOCR / PP-OCRv6 small views | 38/44 | 40/44 | 13 wins, 2 regressions |
| Qwen3-VL-4B 4bit, frozen baseline Top-10 | 39/44 | 41/44 | 13 wins, 1 regression, 3 abstentions |

The exact runtime metadata, OCR artifact SHA256 values, pinned VLM revision and raw outputs are retained in the experiment JSON. All 44 raw VLM responses were revalidated with the final strict parser; decisions did not change. The VLM uses actual query/reference pixels, shuffled public candidate metadata and no ground truth or review text. Its timing sums separately measured stages, excludes model load, and is not measured end-to-end.

All 11 hashes in `data/reviews/baseline_sha256_2026-10-30.json` still match the original baseline reports, labels and catalog. Original per-query rank outcomes were reproduced in identifier, text, image, fused and fused_no_text channels. The 17-error visual review is complete, traceable, non-blind and not expert gold.

## Automated and independent review

- `uv run --extra experiments pytest -q`: 66 passed in the final verification run.
- `node --check web/app.js`: passed.
- `git diff --check`: passed before staging; staged changes checked again before commit.
- Independent source review: all consequential findings resolved. Parser, visual-cache and smoke-output fixes have RED-to-GREEN regression tests. See `2026-10-30-code-review.md`.

## Browser and live inference

Tested the actual local app at `http://127.0.0.1:8765` in the Codex in-app browser:

- Loaded all 44 samples and all five measured runs; baseline-error filter correctly contains 17 samples.
- Switched engines on the same image and confirmed before/after candidate changes. NE555/20729665 changes from incorrect LM7805 to NE555 under RapidOCR views.
- Verified preset image crops/rotations and matching SVG boxes. Browser testing caught an SVG `hidden` attribute bug; the shared show function now toggles the actual attribute. The original failing scenario now has three visible polygons and a nonzero overlay rectangle.
- Uploaded the actual local NE555/20729665 JPEG through the file chooser, enabled multi-view OCR and ran real local inference. The response returned `NE555N FEF2209 8809VL`, NE555 as Top-1 and three visible OCR boxes over the client-generated selected crop. No dataset filename or ground-truth label was supplied for live inference.
- Confirmed VLM summary displays 39/44 and explicitly explains the cached-baseline-plus-generation timing scope. Uploaded-image mode is labelled real-time OCR and does not imply live VLM inference.
- Tested the narrow responsive layout (375 CSS px content width); document width had no horizontal overflow. Reset the temporary viewport override.
- Browser console contained no warning/error entries in the final checks.

Screenshots: `docs/screenshots/workbench.jpg` (final desktop, visible OCR boxes and five measured runs), `docs/screenshots/workbench-mobile.jpg` (narrow layout and actual live upload).

## Decisions and practical limits

The approved work was implemented in the existing clean checkout on the new `experiment/ocr-rerank-demo` branch so existing local data and model caches remained usable. The page uses a loopback stdlib Python server with buildless HTML/JS; MLX has an isolated environment and a pinned package lock. No cloud inference, training or hosted publication was needed.

The four OCR conditions combine model comparison with a separate eight-view/catalog-guided-selection ablation. This is development evaluation on the unchanged 18-class catalog and model-generated labels, not a new blind test. The VLM's single extra correct result over RapidOCR views does not establish a significant advantage; it is much slower and some explanations contain inconsistent package descriptions. A selective OCR/VLM router and a combined new-OCR-plus-VLM pipeline have not been evaluated. The recorded VLM path is Apple Silicon-specific; CUDA VLM deployment remains untested.
