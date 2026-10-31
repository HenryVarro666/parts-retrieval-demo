# Independent review: public same-object triplets

Reviewed 2026-10-31 against `docs/superpowers/plans/2026-10-31-public-triplets.md`.

- Base: `3855480405a634296a2253e7b8a26a5d6adaa292`.
- Frozen data HEAD: `8f3e44d59172b0de7a42ae1104f208a42f365ce7`.
- Implementation: the working-tree evaluator, preparation script, web payload/UI, translation collection and changed tests present during this review.
- This was a read-only review of implementation/data/results; only this review file was added. Sequential model measurements were in progress. No models, training, broad test suite or concurrent benchmark were started by the reviewer.

## Strengths

- `evaluate()` passes only neutral image paths to inference and attaches the source/attribution dictionary after `compare_paths()` has returned. The ground-truth `part_id` is used for scoring, not to build candidate/VLM requests.
- Views 2 and 3 receive their own `run_group()` calls after the predetermined first-view/three-view comparison. The supplementary denominator is 24 single-photo measurements clustered in 8 objects, and the paired denominator remains 8 objects. The summary and per-object replay preserve that distinction.
- The loader binds source and crop hashes, checks deterministic integer crops, excludes catalog page IDs/pixels and rejects repeated canonical capture metadata within a triplet. The frozen selection is bound to the manifest.
- Capture kind, historical overlap, difficult views and the lack of owner/expert confirmation are explicit. All 24 target crops were visually inspected using two temporary contact sheets; the selected targets and declared difficult views were consistent with the manifest. This inspection supports the declared exploratory interpretation, not confirmed physical identity.
- Source credit and the actual independently measured single-view output are exposed in replay. The new UI regression checks that the standalone output can differ from the fused result and that photo-specific source credit/timecode remains visible.

## Issues

### Critical

None found in the reviewed change.

### Important

1. **P2: An optional flag becomes mandatory when the output filename starts with `public_`.**
   - Location: `partsid/multi_image_experiments.py:276`–`285`, particularly the unconditional `summary['all_single']` and `pair['single_photo_records']` accesses.
   - The CLI intentionally makes `--all-single-views` optional. A valid regular paired run saved as `results/multi_image/public_regular.json` passes `validate_saved()`, but the automatic final `report()` raises `KeyError: 'all_single'`. The result JSON has already been written when this failure occurs; later report generation also keeps failing while that valid file exists.
   - Reproduced without models: create a normal completed evaluator fixture with `completed(tmp_path)`, write it as `results/multi_image/public_regular.json`, then call `report(tmp_path)`. Observed `KeyError 'all_single'`.
   - Consider selecting the detailed public section from validated document capabilities/cohort metadata and guarding optional all-single fields. Preserve the ordinary paired summary for runs lacking supplementary measurements. Add a fixture regression for this valid filename/flag combination.

### Minor

1. **P3: The quality stratum name omits a condition that it includes.**
   - Location: `data/public_triplets/selection.json:258`, with the explanation at line 263 and the third-view quality flags later in that group; the generated manifest mirrors it.
   - ATMEGA328P belongs to `blur_or_occlusion`, but the declared stress condition is glare/unreadable marking. Its photos have no `blur` or `partial_occlusion` flag. Therefore describing the resulting four-group stratum simply as “blur/occlusion” overstates that category's specificity.
   - Preserve the frozen selection and explain the existing stratum as a broader marked-quality-stress group in the report/display, or explicitly document that this name includes glare. A future cohort can adopt a clearer category before freezing.

## Verification and provenance spot checks

- Five focused evaluator tests passed: duplicate canonical metadata (three parameter cases), catalog page-ID exclusion, and independent per-view execution/order replay. Command: `.venv/bin/python -m pytest -q tests/test_multi_image_experiments.py -k 'metadata_rejects_same_capture or catalog_capture_id or each_view_is_measured'`.
- All three tests in `node --test tests/web_app_multi.test.cjs` passed.
- Saved EXIF capture dates, where present in the source files, agreed with the declared local date strings. Unknown timezones remain unknown.
- Sampled primary Commons pages agreed with the metadata: [SparkFun13711-01, CC BY 2.0](https://commons.wikimedia.org/wiki/File:SparkFun13711-01.jpg), [Revox installed daughterboard, CC0](https://commons.wikimedia.org/wiki/File:Revox_B215_-_implanting_signal_relays_04_-_implant_in_place.jpg), and [Neo-Geo AES FL, author public-domain declaration](https://commons.wikimedia.org/wiki/File:Neo-Geo-AES-Opened-FL.jpg). This was a spot check, not a legal opinion or independent revalidation of every source page.
- The mandated code graph was queried first; it returned zero indexed changed functions/flows. Focused diff/source reads were used because the graph did not cover the implementation.

## Declined to judge

- Owner/expert confirmation of physical-unit identity: unavailable by design and explicitly disclaimed; visual consistency is the supported evidence level.
- Population accuracy or a blind holdout claim: the frozen, selected stress set is expressly not representative and has declared historical overlaps.
- Final VLM accuracy/latency, translation warmup completeness and full-suite/browser acceptance: model measurements and parent-owned verification were still in progress at review time.
- Final private GitHub push, remote visibility and fresh-clone reproduction: subsequent parent-owned delivery work, not completed evidence available to this review.

## Assessment

**Ready to merge: With fixes.** The core measurement, denominator and inference-boundary changes are sound in the reviewed implementation. Fix the reproducible report-generation compatibility bug, then complete the already planned numeric, browser and fresh-clone acceptance checks. No model tuning or data reselection is recommended from these review findings.

## Independent follow-up acceptance

The parent requested a focused review of the fixes while forced-VLM measurements were still running. The code graph was checked again and remained unindexed; the reporting guard, regression test, localized quality labels and new expandable strata renderer were inspected directly.

- **P2 resolved.** The public-detail section now requires both cohort metadata and `all_single_views`; ordinary paired results remain in the main report. The new `test_public_named_run_without_optional_all_single_views_can_be_reported` passed independently (1 passed, 14 deselected). An additional temporary-fixture matrix checked three cases: cohort without all-single measurements, cohort with all-single measurements, and all-single measurements without a cohort. Every case reported successfully; only the second received the optional public-detail section.
- **P3 resolved through presentation clarification.** Chinese, English and Spanish now describe the existing quality category as having an unreadable-marking view, including glare. Report prose also names glare. `git diff --exit-code 8f3e44d59172b0de7a42ae1104f208a42f365ce7 -- data/public_triplets/selection.json data/public_triplets/manifest.json` passed, confirming that these frozen files were not altered to make the reporting change.
- **New strata display accepted.** A small independent DOM-harness probe rendered a quality-stratum fixture in each of `zh`, `en` and `es`. All three rendered the localized heading/quality label and the supplied `2/4 → 3/4` counts without leaking translation keys. The renderer uses the saved paired first-view/three-view denominators.
- **Node verification:** all 3 multi-photo UI tests and all 8 i18n tests passed independently. No model calls or heavy CPU/ML verification were run by this reviewer.

**Updated assessment: Accepted for the reviewed code changes.** No critical or important review findings remain open, and the minor quality-label issue is addressed. Final numeric acceptance, real-browser verification, translation-cache warmup and remote/fresh-clone delivery checks remain with the parent as previously scoped; this follow-up does not claim those stages are complete.

## Focused review: web validation cache

The parent subsequently added a result-byte-digest cache to avoid repeating decoded-pixel/provenance validation for every web/API/image request. This follow-up reviews that additional change; it supersedes the preceding acceptance only for the new cache implementation.

### Important: P2 cache hits do not track every logical dependency

- Location: `partsid/web.py:93`–`101`, with the snapshot canonicalization at `partsid/multi_image_experiments.py:164` and initial validation at `partsid/multi_image_experiments.py:170`–`187`.
- The cache correctly hashes result bytes and rehashes every listed `sources_sha256` file. However, a successful initial `validate_saved()` does not establish that this dictionary covers every dependency it validated. Also, the evaluator stores resolved source paths, losing the relationship between a manifest's logical path and a symlink target.
- **Missing-entry reproduction:** generate the normal tiny completed fixture; remove only `data/0.png` from `sources_sha256`; save it and call `multi_payload()` once. This result passes initial validation. Change `data/0.png` while leaving all other files alone. Direct `validate_saved()` now raises `Stale photo hash`; the cached `multi_payload()` still returns the run.
- **Evaluator-generated symlink reproduction:** before evaluation, make manifest photo `data/0.png` a symlink to `data/first-target.png`. Evaluate normally and save the returned document without edits. Its source dictionary contains `data/first-target.png`, not the logical `data/0.png` path. After the first accepted payload, retarget `0.png` to `1.png`. Direct validation rejects the stale photo; cached `multi_payload()` continues returning it because all saved canonical source hashes are unchanged.
- This permits a saved replay to show measurements for earlier pixels while the image route resolves to changed pixels. The optimization therefore changes the previous validation behavior for results the existing validator accepts.
- Consider establishing complete logical dependency coverage before caching and checking those paths, resolved targets and byte hashes on every hit. A conservative alternative is to bypass the cache when coverage is incomplete or logical dependencies use symlinks. Retain regressions for both cases; checking only mtime preservation does not cover them.

### Other cache/UI checks

- Root/result-path isolation, SHA256 result-byte invalidation, containment/existence checks for declared sources, and lock protection of cache initialization are sound in the inspected code.
- `test_web_validation_cache_reuses_only_unchanged_result_and_source_bytes` passed independently (1 passed, 15 deselected). The 3 multi-photo UI and 8 i18n Node tests also passed. The new call-count labels count paired actual VLM calls with the paired object denominator; the additional historical-source-overlap wording is consistent with the frozen metadata.
- Both new reproductions used small temporary fixtures. No models or heavy CPU/ML checks were run, and no implementation/data/results files were edited by the reviewer.

**Cache assessment: With fixes.** Address the reproduced dependency invalidation gap before accepting this additional optimization. Earlier accepted measurement/UI changes and the parent-owned final delivery checks retain their prior scope.

## Cache fix: independent acceptance

The parent added exact snapshot coverage validation and a separate logical-path fingerprint. The follow-up inspected `source_dependencies()`, `source_snapshot()`, `replay_fingerprint()` and `multi_payload()` together. Dependency enumeration now comes from the fixed data inputs, catalog-reference paths, manifest/selection and query/source paths rather than trusting the stored receipt's list. Each fingerprint entry retains the logical path, resolved target and SHA256; cache misses receive full validation followed by another fingerprint comparison.

- **Missing-coverage and basic symlink cases:** the three focused regressions passed independently: `test_web_validation_cache_reuses_only_unchanged_result_and_source_bytes`, `test_replay_requires_complete_dependency_hash_coverage` and `test_web_cache_detects_a_retargeted_query_symlink` (3 passed, 15 deselected).
- **Shared-target case:** an additional independent temporary fixture made query `0.png` a symlink to `first-target.png` and also declared `first-target.png` as the original full-size crop source. After warming the cache, `0.png` was retargeted to `1.png`. The aggregate canonical `source_snapshot()` dictionary remained exactly unchanged because both targets were still dependencies. Nevertheless, the per-logical-path `replay_fingerprint()` changed, and `multi_payload()` rejected the replay. This verifies the requested case where aggregate canonical hashes alone cannot detect the changed binding.
- **Change during validation:** a temporary instrumentation probe changed a source's bytes immediately after successful full validation. The second fingerprint check rejected that unstable replay; restoring the original source then allowed validation again.
- These checks used tiny temporary fixtures only. No implementation/data/results files were edited by this reviewer, and no model calls were made.

**Final code-review assessment: Accepted.** The new cache P2 is resolved, including the shared-target case. No critical or important findings remain open from this review. Final numeric/browser/translation-cache and remote/fresh-clone acceptance retain the parent-owned scope recorded above.
