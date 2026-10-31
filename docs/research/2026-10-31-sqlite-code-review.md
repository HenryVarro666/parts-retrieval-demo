# SQLite candidate pipeline code review

Review base: `d4cd746`. Scope: the new SQLite, shape, candidate runtime/runner, tests and changed web/evaluation files, including untracked files. The graph-first entry returned `empty_graph`; its zero-node change analysis could not cover this implementation, so source inspection used the permitted fallback. This reviewer changed only this report, ran no models, and installed no dependencies.

**Recommendation: PASS for the reviewed scope.** No unresolved material findings remain. The three initial P2 findings below were fixed and received targeted re-verification. All five final stages contain the correct 44 unique queries and pass current-source fingerprint validation.

## Resolved findings

### Resolved P2: Present-but-empty SQL results were shown as missing records

`web/app.js:536-560` uses candidate presence as record presence. A saved SQL result with `rankings.sql=[]` receives “暂无记录” and “等待记录”, although it is a completed retrieval miss. In the current data, seven SQL results are empty; `ATMEGA328P/133222141.jpg` and `I8086/15625453.jpg` were baseline-correct and therefore are actual regressions. Aggregate metrics already count these misses correctly.

Suggested fix: pass record presence separately to status/change rendering. A present empty ranking is an incorrect no-candidate result; baseline-correct plus current-empty is a regression. Reserve the waiting state for absent records. Verify both cases with DOM coverage.

Resolution verified: status rendering now receives `hasRecord`, and comparison logic checks record presence independently of candidate presence. An isolated DOM-stub execution of the actual functions confirmed that a saved empty SQL result is marked incorrect and a regression, while an absent record retains “暂无记录” / “等待记录”.

### Resolved P2: Completion and comparisons did not require the full aligned query set

`partsid/candidate_experiments.py:40-54,97-108,137-149` trusts the requested completion flag rather than checking the expected files, unique records and labels. A model-free temporary-directory probe passed only the first record to `stage_document(..., complete=True)`: it produced `status=complete`, `n=1`, `top1=1.0`; `compare` then included it as `1/44` and claimed an unchanged 44-image evaluation. `vlm` also accepts such a document.

Suggested fix: validate exact expected query-file and label alignment, uniqueness and required channels before accepting complete input or generating comparison rows. Partial checkpoints should remain available with a non-complete status. Test missing, duplicate and mismatched-label records. Current real staged documents each contain the correct 44 unique queries.

Resolution verified: `validate_rows` rejects incomplete, duplicate, unknown-file and mismatched-label records before a complete stage is written. `validate_source` requires this alignment before and after VLM processing and before comparison; report denominators use validated record counts. Partial checkpoints remain non-complete. The regression tests pass, and all five final documents pass exact 44-query alignment.

### Resolved P2: Runtime and batch provenance checks omitted source changes

`partsid/candidate_pipeline.py:169-173` verifies the public catalog hash but not the stored reference-manifest hash. A model-free probe built a temporary DB from the original references, changed one reference filename in `labels.csv`, and confirmed that `make_candidate_pipeline` accepted the stale DB and consumed the changed references.

`partsid/candidate_experiments.py:97-110` also consumes saved OCR/shape records without comparing their source hashes to the current labels/catalog/database/reference pixels. Base stage records lack a query-pixel fingerprint. Changing a query or reference after `run` can silently combine old OCR/shape evidence with newly read VLM pixels while retaining the old “fresh” source configuration.

Suggested fix: reject a mismatched canonical reference manifest before constructing models; retain each stage input's pixel hash; verify saved stage fingerprints against current sources before VLM preparation. Test with changed references/query pixels and stubbed model constructors/workers. The current on-disk labels, DB and reference-pixel hashes match the staged records.

Resolution verified: the factory checks canonical catalog and reference-manifest hashes before model construction. `validate_source` now checks the public catalog, labels, DB, all raw query images, reference manifest and reference images. Current-source validation runs before and after VLM processing and during comparison. Seven provenance tests pass, including changed catalog metadata, query/reference bytes, DB/labels, incomplete/duplicate/wrong-label rows, and a stale reference manifest failing before encoder construction. Root reran all 44 OCR records with fingerprints captured before the measured loop; final saved fingerprints independently match current sources.

## Verification and strengths

- `uv run --extra experiments pytest -q tests/test_sqlite_catalog.py tests/test_shape.py tests/test_candidate_pipeline.py tests/test_web.py tests/test_experiments.py`: **63 passed**.
- Targeted recheck after fixes: `uv run --extra experiments pytest -q tests/test_candidate_provenance.py tests/test_candidate_pipeline.py tests/test_web.py`: **16 passed**. Root separately reports **133 passed** for the full suite; this reviewer did not rerun that full suite.
- Independently recomputed all 44 saved SQL receipts and strong IDs, candidate pools/origins, reference-shape comparisons and post-shape order. All matched.
- Recomputed all three completed stage summaries, checked exact query/label alignment, catalog-manifest/database/reference-pixel hashes and cumulative stage timing. All matched. The fixed gate accepts 36 records and finds one conflicting OCR-view record.
- SQL-only: Top-1/Recall@10 **36/44**. Hybrid: Top-1 **38/44**, Recall@10 **42/44**. Shape: Top-1 **38/44**, Top-3 **40/44**. Query shapes are available for **10/44**.
- Independently checked all 44 fresh VLM requests against the saved new pools, both actual input images, prompt hashes, shuffled public fields and shape inputs. Reparsed all 44 raw responses and recomputed saved promotions, gate decisions, summaries and per-record timing sums; all matched. The candidate-source file hash also matched.
- New-pool VLM: Top-1/Top-3 **42/44**, six abstentions, **+5 / −1** versus RapidOCR and **+15 / −0** versus the original baseline. Gated projection: Top-1 **41/44**, Top-3 **42/44**, eight projected calls and two consulted abstentions, **+4 / −1** versus RapidOCR and **+15 / −1** versus the original baseline. Both retain Recall@10 **42/44**. Unused VLM evidence/time is removed from projected gate records.
- The first new-pool VLM batch executed by root generated all 44 raw checkpoints. After the provenance fix and fresh OCR rerun, the final rebuild records **0 new generations / 44 validated cached generations**, with **44 batch-verified queries**. The reviewer checked every reused checkpoint against the current new candidate pool, prompt and both actual VLM image hashes. These are the same new-pool forwards, not old EasyOCR-pool decisions. The gate's eight calls remain a projection; the measured VLM stage time retains original checkpoint generation times and is explicitly not the wall time of the cache-reuse pass.
- Final targeted audit passed all five documents' current-source fingerprints and summaries, exact query/label alignment, VLM candidate-source hash, every reused response's prompt/image hashes, pool-constrained choices, gate flags and stage timing sums. Final Top-1 counts remain **36 / 38 / 38 / 42 / 41** for SQL / hybrid / shape / VLM / gate.
- SQL parameters and quoted FTS tokens avoid OCR operator injection; repeated normalized terms do not multiply votes; empty/noise input does not return the whole catalog. Connections close per query.
- Candidate origins distinguish SQL evidence from visual supplements. Shape remains heuristic, soft and unavailable when unreliable; strong aliases are preserved. No new physical-size/package/pin claims were found.
- Inference does not consume query labels or review transcriptions. New VLM prompts whitelist public catalog fields, use shuffled candidates and constrain parsed selections to the pool; the worker invalidates caches when the prompt or either actual VLM image changes.
- The page explains the original baseline Top-1 as **27/44 = 61.4%**, separates playback/live results, uses text nodes for dynamic evidence, and labels staged VLM timing and gate projections.

## Final presentation recheck

Targeted source and DOM-stub checks passed for the two browser findings. Candidate badges now require a finite per-reference shape score and use “形状阶段 #n”. Executing the actual renderer confirmed that null, missing and nonfinite scores show no shape badge; a finite score shows the stage-rank label; the SQL stage shows no shape badge. The timing-label matcher now accepts the actual `measured fresh cumulative OCR...` configuration: all three final SQL/hybrid/shape documents produce the Chinese explanation of fresh stages, untimed warmup and excluded model loading.

Root separately reports successful real browser live tests: NE555's strong SQL gate skipped VLM (4.60 s including initial loading); a 2N3055 photo with weak OCR and no SQL candidates invoked VLM and returned 2N3055 (9.99 s including process/model loading). These are root's live checks; this reviewer performed only the targeted source/DOM checks above. The review recommendation remains **PASS**.

## Limits

Root owns the full suite, browser/live-upload verification, fresh private-clone checks and final preservation audit. This review validated the saved 44-image new-pool VLM output and its raw checkpoints without executing inference. The dataset remains a small development set with model-generated labels, not a blind or expert-validated accuracy claim.
