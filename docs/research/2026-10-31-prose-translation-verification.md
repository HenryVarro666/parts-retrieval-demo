# Model analysis and review-note translation verification

Date: 2026-10-31. Base: `8dacdba`. The requested change extends the existing Chinese/English/Spanish selector to model analysis and review notes. Raw OCR text, visible markings, observed part numbers, candidate IDs, source records and evaluation results remain unchanged.

## Implementation and translation provenance

- Free prose is translated separately: VLM `reason`, review `comparison_note` and `suggested_action`. Structured review readability, comparison and image-quality codes have human-readable three-language labels. `observed_text` and `observed_part_number` are excluded from translation.
- The local text-only worker reuses the pinned Qwen3-VL 4-bit environment. It receives prose, never query images, evaluation labels or review observations as separate fields. Source text is treated as translation data, not instructions. No cloud translation endpoint is called.
- Markings, part numbers, numeric tokens and uncertain fragments such as `N8028?` are protected before generation. Validation rejects missing, duplicated or unknown placeholders before restoring the exact source strings. Possessive apostrophes do not freeze ordinary English clauses.
- The saved cache contains **118 unique sources × 3 languages = 354 entries**: **118 exact source originals, 165 local-model translations, 71 Codex-assistant post-edits**. The post-edits cover all 34 Chinese review prose strings in both English and Spanish, plus three VLM translations that failed structural validation. The original local drafts and edit provenance are retained; six drafts are explicitly marked rejected. Their failed checkpoint stored key/raw/error only, so deterministic request context was reconstructed and unknown generation timings are recorded as null.
- All 68 bilingual review-note translations were read and edited for uncertainty, negation, foreground/background meaning, image-cropping intent, uncertain characters, and identifier relationships. The three VLM repairs preserve the original analysis claims, including any original factual errors. This is translation review, not expert verification of component identity or model analysis.
- Cache SHA256: `7c2f796b551b7a9559714a80eeb801ff00bb5e70ac64b195ba9d434457c4fe7c`. Each entry binds its exact source, target, pinned model/revision, policy, prompt hash and restored output. Curated saved translations take precedence over older runtime copies.
- New live prose is translated locally on demand and cached only under ignored `data/cache/`. The browser batches requests within eight texts and 12,000 characters, prevents duplicate pending requests, and ignores stale language/sample responses. The service serializes model work with the existing inference lock.
- Translations are labeled; users can expand the exact original analysis or original review notes. A failure shows an explicit unavailable state with the original, rather than presenting a rejected translation as valid. Each generation has at most one stricter retry.

## Checks

- `uv run --frozen --extra experiments pytest -q`: **147 passed in 4.75 s**.
- `node --test tests/web_i18n.test.cjs`: **8 passed**.
- Regression tests observed RED then GREEN for the route, malformed cache output, quote boundaries, unknown placeholder widths, request batching, uncertain fragments, curated-cache precedence, and missing saved-language coverage.
- The full cache test verifies all 354 current entries and excludes any live-only prose from the shipped artifact. All 11 baseline checksums and all **249** data/result files tracked at the base commit are byte-identical.
- [Independent review](2026-10-31-prose-translation-review.md): **PASS**. The reviewer audited final coverage/hashes/provenance, read all 68 edited review translations and three VLM repairs, and exercised 1,980 sample/run/language combinations in the actual app consumer harness. All saved prose replayed without translation requests and source data stayed unchanged. The harness also covered stale responses, errors/retry, no-data live mode, 8+4 batching and oversized-source fallback.

## Actual browser and local-model checks

Used the existing in-app browser and local service at `http://127.0.0.1:8765/`:

- Replayed SQLite VLM sample 2N3055 `80876576.jpg` in Chinese, English and Spanish. The analysis, review analysis, suggested checks, readability and image-quality descriptions followed the selected language. Raw OCR `9 719`, visible marking `LN3055GR R 719`, review transcription `2N3055GR / RCA / 71? / R`, and observed part number `2N3055GR` stayed unchanged.
- Expanded the original analysis and confirmed it still contains the exact English source. Review originals remain available separately. The current sample and model choices survived language changes.
- Uploaded that image and enabled the actual local VLM. The new live analysis was automatically translated into Spanish, then into Chinese after switching languages. The query OCR and VLM observed-text fields stayed raw; candidate 2N3055 and service time **9.70 s** did not change during translation. Translation is a separate operation and is not included in that recorded inference timing.
- On-demand translation showed the localized pending state, then completed. The Spanish live result is a machine translation, with source disclosure, and is less polished than the edited saved review notes. No expert translation quality claim is made for unseen live prose.
- Default browser width and scroll width were both 670 pixels; final console warning/error log was empty. The page was restored to Chinese and retained as the local deliverable.

Screenshots: [Chinese live analysis](../screenshots/prose-analysis-zh-2026-10-31.jpg), [Spanish review notes with raw markings](../screenshots/prose-review-es-2026-10-31.jpg).

## Reproduction and limits

Saved replay uses the shipped JSON cache and does not require MLX or model downloads. `uv run --extra experiments python -I -m partsid.translation warm` reuses valid entries and generates only missing translations when the existing Apple Silicon VLM environment is installed. New live translation is currently tested only on this Mac. Environments, model weights and runtime upload caches remain excluded from Git; the original catalog, labels, model outputs and benchmark files are preserved.
