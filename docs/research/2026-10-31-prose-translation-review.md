# Analysis and review-prose translation review

Date: 2026-10-31
Base: `8dacdba`
Scope: uncommitted translation backend/worker/tests, web route and payload, prose cache, async UI, review-code localization, and frozen translation export. No implementation edits or model execution were performed by the reviewer.

## Strengths

- Translations are separate from source experiment/review records. OCR observations and part-number fields stay raw; translated prose is labeled and the original remains expandable.
- Backend cache validation binds exact source, target, pinned model/revision, policy, prompt hash, and parsed output. Protected identifier occurrences are counted rather than compared as a set.
- The async UI cache uses exact source plus selected language. The consumer harness confirms that late responses from a different language or sample do not replace current prose, and that failed translations expose the original and a working retry action.
- Warm export collects only VLM reasons and the two intended review prose fields. The final 118-source frozen artifact contains no source outside that allowlist. Runtime cache files are covered by the existing `data/cache/` ignore rule, and the curated frozen entries take precedence over older runtime copies.

## Findings

### Critical

None found.

### Important

1. **[P2, resolved] Avoid protecting ordinary English between apostrophes.**

   The initial `SPANS` quoted-span pattern in `partsid/translation.py` treated possessive apostrophes and internal copyright apostrophes as quoted-marking boundaries. For example, `I8088's 40-pin DIP form factor. The text 'iP8088-6'` protected the entire substring `'s 40-pin DIP form factor. The text '`. Structural validation then required the English clause to survive unchanged in Chinese and Spanish.

   At least 17 of the 118 saved sources had ordinary English prose inside protected spans. Checkpoint key `51ff7d98eca315c9ff9c05c978ce4dbbb9423c9f7aa2f4de479206d1fa32879b` retained a long English clause in Spanish; `6894e2284e73f43b76e6b0c776d79f7290b95cd27e65553bd7108b0a82803cd2` did the same in Chinese. Other affected topics included LM7805, I80286, ESP8266, and UA741.

   Resolution: the executor tightened quote boundaries and only protects whole quoted spans when their tokens resemble markings. The regression test passes, all final entries match current prompt fingerprints, and regenerated I8088/LM7805/I80286/ESP8266 samples no longer retain the previously frozen English clauses. All 118 current source masks were checked for the ordinary clauses identified in this finding.

2. **[P2, resolved] Split the UI queue to respect translation request bounds.**

   The initial `flushProse` gathered every queued source for one language and sent it in one request. `partsid/translation.py`, `translate_texts`, accepts at most eight texts and 12,000 source characters. The consumer harness coalesced four sample renders before the zero-delay flush and observed a 12-text request. The server rejected that request before generation, and the client marked all those notes failed even though each note was individually valid.

   Resolution: `I.proseBatches` now partitions the per-language queue by both count and character limits, and each actual batch retains its own pending/failure bookkeeping. The consumer recheck completes all 12 sources through requests of eight and four texts without failure. The Node tests also check 4,000-character sources partition into batches of three and one.

3. **[P2, resolved] Reject malformed persisted translation output without breaking experiment loading.**

   The initial `parse_translation` called `.strip()` on non-string `raw` values; `valid_entry` did not catch the resulting `AttributeError`. The existing test `test_cache_rejects_source_language_model_or_output_drift` failed with `raw=123`. Such an entry could also interrupt `translation_payload` and `/api/data`.

   An explicit raw-string guard now raises `ValueError`; the regression test and focused Python suite pass.

4. **[P2, resolved] Reject unknown placeholder widths as well as three-digit placeholders.**

   The initial `TOKEN` in `partsid/translation.py` only recognized `__KEEP_` followed by exactly three digits. Consequently `parse_translation` accepted invented `__KEEP_1__` and `__KEEP_1000__` when the source had no protected spans. These were rendered literally and contradicted the promised unknown-placeholder rejection.

   Resolution: validation now recognizes differing digit widths and alphanumeric KEEP marker bodies and requires the exact issued-key multiset. The three demonstrated unknown forms (`__KEEP_1__`, `__KEEP_1000__`, `__KEEP_X_1__`) are rejected in both regression tests and the reviewer recheck.

5. **[P2, resolved] Display immediate fallback for an individually oversized note.**

   The first client-side bound guard marked a 4,001-character source failed inside `queueProse`, after `proseElement` had already read its failure state. Its first render said translation was pending with no request or timer scheduled, so it could wait indefinitely.

   Resolution: `proseElement` queues or rejects before selecting the display state. The consumer recheck confirms immediate unavailable/original disclosure, zero requests/timers, and no futile retry button for an oversized note.

### Translation quality and provenance

- Initial drafts included mixed-language prose, a mistranslation of catalog alias coverage, a changed foreground/background selection, conditional wording that weakened the prohibition on generative restoration as text evidence, loss of uncertain-character notation, and an instruction that described physical cutting instead of cropping an image. These were reported to the executor.
- The executor completed assistant post-edits for all 34 Chinese review sources in both English and Spanish, plus three VLM outputs rejected by structural validation. The reviewer read all 68 final review translations and all three final VLM repairs against their sources. The identified defects are fixed; negation, uncertainty, dates, spatial selection, OCR-only-third-line diagnosis, and image-processing instructions retain their source meaning.
- The final artifact contains 118 exact source originals, 165 local-model translations, and 71 assistant post-edits. Every post-edit retains its draft, source/target/prompt context, editor, and edit note. Six drafts were structurally rejected outputs: they are explicitly flagged, their raw responses still fail parsing, their reconstructed context is labeled, and their generation timing remains unknown. Other retained drafts independently validate as local-model entries.
- Trailing uncertainty markers such as `N8028?` are now protected and covered by regression tests. Every final entry preserves the source numeric/alphanumeric-token multiset, and no unresolved KEEP marker or Chinese script remains in English/Spanish translations.
- Regenerated VLM examples were also sampled for language, negation, identifier, and date fidelity. This is translation review, not certification of the original component claims or of every unedited generated sentence.

## Validation

- Required graph tools were consulted first. The graph has no indexed nodes, so source review and focused execution were used.
- Initial focused Python result: one failure (`raw=123`) and 14 passes. Final focused result: 18 passes across `tests/test_translation.py` and `tests/test_web.py`.
- Node catalog/cache/batch tests: 8 passed.
- Consumer VM harness evaluates the actual current app/catalog with a minimal DOM and controlled network/timer boundaries. It covers late language/sample responses, exact cache lookup, original disclosure, review-code localization, raw OCR/markings preservation, retry after failure, live translation without saved data, 12 sources completing as eight plus four, and immediate fallback for an oversized source.
- Exercised generation retry with a subprocess stub rather than a model: exactly attempts zero and one, distinct prompt hashes, a valid attempt-one cache entry on second-attempt success, and a clean error after second-attempt rejection.
- Rechecked all 118 source masks: none contains the previously identified ordinary English clauses inside protected spans.
- Final frozen cache: exactly 354 unique keys and source/target pairs covering every one of the 118 allowlisted sources in Chinese, English, and Spanish. All source hashes, prompt hashes, model/revision/policy fields, final parsed outputs, and retained draft provenance validate. No source-original entry changed its text, and no source from a live upload was added to the frozen artifact.
- Exact audited `data/translations/prose.json` SHA-256: `7c2f796b551b7a9559714a80eeb801ff00bb5e70ac64b195ba9d434457c4fe7c`.
- Evaluated the actual `web_payload` through the consumer VM: 1,980 sample/run/language combinations, 759 VLM prose views, and 1,530 review prose fields all render from cache with zero translation requests and unchanged source data. Runtime-only local prose may appear in the API payload; it remains outside the frozen export.
- Saved-prose inventory: 118 unique sources, maximum source length 562 characters. No saved source exceeds the individual 4,000-character backend limit.
- `git diff --check` passed at the inspected revision.
- Source experiment results, raw review records, labels, and part catalog have no diff against `8dacdba`.
- No shared-browser interaction, model generation, installation, or implementation mutation was performed by the reviewer. Browser rendering and actual live-model behavior remain the executor's separate verification responsibility.

## Declined to judge

- Correctness of the original VLM component claims and model-assisted review labels: the requested change translates existing analysis, while retaining the source and its provenance; it does not authorize rewriting inference evidence.
- Model accuracy and inference performance: unchanged by this translation layer, and no model was executed for this review.

## Assessment

**PASS.** All code and artifact findings are resolved. The focused tests, stale-response/retry checks, final cache audit, complete review-note translation read, and actual-payload consumer sweep pass. No open finding remains in the reviewed scope.
