# Independent multi-image branch review

Reviewed base `95923ed21631099a7e1e53bdc1d411a5470d36c7` through head `518517696adcf0f595aac42f9a009052d68dedea` on 2026-10-31. Requirements: `docs/superpowers/specs/2026-10-31-multi-image.md` and corresponding implementation plan. This report describes the reviewed head; subsequent fixes need a follow-up check.

**Assessment: changes requested before merge.** Five actionable findings: two provenance-validation gaps and three UI/state issues. The committed example results are correctly marked exploratory/control; the provenance findings concern inputs and saved records that the validation boundary currently accepts, not evidence that the committed measurements were fabricated.

The implementation has sound separation between inference and labels, fresh first-photo/all-photo extraction, exact-pixel reuse within a group, grouped vote weights, explicit identifier conflicts, and constrained candidate selection. Existing related tests pass. The gaps below concern boundaries those tests do not exercise.

## Findings

### 1. 🔴 P1 — Saved replay trusts scope without validating grouping provenance

**Location:** `partsid/multi_image_experiments.py:117–140`, consumed by `report` at lines 174–177 and `partsid/web.py:82–87`.

`validate_saved` checks the hashes that a document lists, numerical summary consistency, labels, and photo order. It never checks the allowed scope, grouping provenance, distinct query pixels, or consistency between the embedded groups/scope and the hashed input manifest. The strict checks in `load_manifest` are bypassed during report regeneration and saved replay.

**Reproduced without modifying any repository files:** load either committed `paired_retrieval.json` or `duplicate_control.json`, change only `doc['scope']` to `confirmed_same_object`, then call `validate_saved(doc, root)`. Both pass. The former still has `identity_basis.status == 'visually_supported'`; the latter has no identity provenance and repeats each input three times. `report` would count the latter as 44 confirmed objects because it trusts the accepted scope.

**Suggested fix:** share a group/provenance validator between ingestion and replay. For paired runs, require allowed scope, identity evidence compatible with scope, three distinct capture identities, current photo/source hashes and catalog exclusion. Bind the embedded scope/groups to an explicitly identified, hashed manifest. For controls, enforce the control-specific repeated-input structure and never allow promotion to paired scope. Require complete source coverage rather than merely validating whichever source keys happen to be present.

**Regression coverage:** rejecting scope-only promotion of both actual saved documents, unsupported scope, omitted required source hashes, and mismatch between embedded groups and the current hashed manifest.

### 2. 🔴 P1 — Three crops of one capture pass as a real three-photo group

**Location:** `partsid/multi_image_experiments.py:62–81`.

The validator correctly reconstructs declared crops, but only requires distinct *derived* pixels. Three slightly different crops of the same original image therefore satisfy its three-photo requirement. This turns one capture into a purported paired multi-photo experiment despite known source provenance showing there was only one capture.

**Reproduced:** create one 80×60 source image and crop it with `[0,0,80,60]`, `[1,0,80,60]`, and `[0,1,80,60]`. Supply correct hashes/crops, `scope: confirmed_same_object`, and `identity_basis: {status: user_confirmed, evidence: 'Same component'}`. `load_manifest` accepts the group. Identity confirmation does not establish that three separate photos were captured.

**Suggested fix:** derive a capture identity from the declared source image when present, otherwise the query image, and require distinct capture pixel fingerprints for paired groups. Detect copied source files by pixels rather than path alone. Route known single-capture crops/derived variants to an explicit control scope or reject them. Apply this rule in replay validation as well.

**Regression coverage:** different crops of one source and differently named exact copies of one source must fail paired validation; the existing fixture with three distinct source captures must continue to pass.

### 3. 🟡 P2 — An invalid upload can leave the UI permanently in reading state

**Location:** `web/app.js:808–813` and `822–827`; disabled controls at lines 329 and 715.

`readUploads` increments `uploadSequence` before validation. If a valid FileReader is still pending and a second invalid selection/drop arrives, the second invocation returns before owning or clearing `state.live.reading`. The first invocation then sees a stale sequence and its `finally` does not clear the flag either.

**Reproduced using the actual function body in Node VM with a deferred FileReader:** start a valid upload, call `readUploads` with four valid image files before the first read completes, then complete the first reader. `state.live.reading` remains `true`, the old image remains selected, and Predict and saved replay remain unavailable. Another successful upload or page reload is needed for recovery.

**Suggested fix:** validate before invalidating the currently active read, or explicitly finish/cancel the active read state on the invalid-selection branch. Keep ownership of the reading flag and sequence cancellation consistent. Test the async coordinator, not only `PartsMulti.fileError`.

**Regression coverage:** valid pending read followed by too-many/oversize/unsupported files; latest valid selection wins; failures restore Predict/replay availability.

### 4. 🟡 P2 — Selected-photo OCR is paired with first-photo identifier hits

**Location:** `web/app.js:421–431`; first-photo carryover originates in `partsid/multi_image.py:94`.

`renderEvidence` selects the current photo for OCR and shape, but reads `id_hits` from the fused record. Fusion deep-copies photo 1 and never replaces that field. Selecting photo 2 can therefore show photo 2's OCR and shape alongside photo 1's identifier hits; identifiers found only in later photos never appear in that section. If this section is intended as aggregate evidence, it is also incomplete because it contains only the first photo.

**Reproduced:** fuse two fixture records with `id_hits=[['A',1,'A123']]` and `id_hits=[['B',1,'B456']]`. The fused record has strong IDs `['A','B']` but `id_hits` remains only `A123`. The UI's identifier section reads that same list for either photo selection.

**Suggested fix:** use the selected `photo.id_hits` for the per-photo identifier section and label its photo context. If aggregate identifier evidence is desired elsewhere, explicitly merge hits with photo provenance instead of carrying photo 1 forward. Preserve the raw aliases. Consider the candidate-card identifier badge separately, since it also uses the fused first-photo-only field.

**Regression coverage:** switching between two photos with different or absent identifier hits updates OCR, geometry, and identifier evidence together, including after language/translation rerenders.

### 5. 🟡 P2 — Saved table calls selective visual runs “forced” and ignores confirmed scope

**Location:** `web/app.js:708`, `partsid/web.py:85–87`, and `web/i18n.js` keys `multi.visualRun` / `multi.retrievalRun`.

The table chooses its label solely from `visual_enabled`; that label is always “Forced visual check · exploratory.” However, the documented `--visual` command enables selective gating, while only `--visual --force-visual` forces execution. A normal run may skip VLM in either or both paths and still be labelled forced. Likewise, a valid user-confirmed custom manifest is labelled exploratory because the row ignores that scope. The backend drops `force_visual` from its payload, making the distinction unavailable to the current renderer.

**Reproduction:** run the documented manifest command with `--visual` and without `--force-visual`, save under a new result name, and inspect the table. The label expression selects the same text used by the committed forced run regardless of the decisions. This follows directly from the payload and renderer; no additional model generation was needed for review.

**Suggested fix:** propagate `force_visual` and preserve scope in separate translated labels. Distinguish retrieval-only, selective visual verification, and forced visual verification. Display actual per-path VLM execution from the saved decisions without inferring execution from configuration.

**Regression coverage:** table rendering for retrieval-only, selective VLM with zero/one/two actual calls, forced VLM, confirmed/exploratory groups, and duplicate controls.

## Verification and remaining boundaries

- Graph-first review attempted: `get_minimal_context_tool` returned `empty_graph`; `detect_changes_tool` returned changed files with zero graph nodes/functions. Source/diff fallback was therefore necessary; the graph's zero risk score is not assurance.
- Independently ran the focused Python suites: **37 passed** (`test_multi_image`, `test_multi_image_experiments`, `test_web`, `test_translation`).
- Independently ran Node suites: **12 passed** (`web_multi_image.test.cjs`, `web_i18n.test.cjs`).
- Ran pure probes for findings 1–4. Repository input/output artifacts were not altered; the single-capture fixture used a temporary directory. Finding 5 was established from the actual payload and rendering branches.
- Checked grouped support and fused shape arithmetic: available scores use group-normalized weights; unknown scores are omitted rather than zeroed. No concrete arithmetic defect found. The displayed fused shape score could be labelled as an aggregate to clarify its relation to the selected photo, but this is not an additional blocker.
- Conflict-aware direct acceptance, duplicate normalized support, invalid-third-image/legacy multi-input rejection before model initialization, frozen VLM candidate enforcement, and separate fresh paired extraction have explicit implementation/test support.
- Did not rerun heavy models or browser automation, per review scope. Parent-reported runtime/browser checks and the complete 166-test Python run were not independently repeated here. This review makes no new claim about physical identity, multi-angle population accuracy, CUDA support, or production readiness.

**Declined to judge:** []

Fix the five findings with targeted regressions, rerun the relevant suites, and perform a focused follow-up review before private synchronization/merge. The committed exploratory fixture and existing measured outputs can remain intact while these boundary checks are tightened.
# Parent verification addendum — 2026-10-31

All five findings below were reproduced in failing behavior tests before the corresponding fixes, then passed. Full final suite: **169 Python tests + 15 Node tests**. This is author verification after the independent review, not a second independent approval.

- Saved scope is now bound to the original hashed manifest, including scope and exact groups; duplicate controls must contain repeated pixels and cannot be promoted to confirmed pairs.
- Paired manifests require three distinct source captures, including parent pixel fingerprints for crops.
- Invalid file batches no longer cancel an in-flight valid selection or strand the reading state.
- Active-photo identifier hits follow the displayed photo, while fused candidate rankings remain unchanged.
- Saved API/UI retain and distinguish forced/selective VLM policy and confirmed/exploratory/control scope.

The measured paired outputs were unchanged; two saved result documents gained an explicit pointer to their already-hashed source manifest. No VLM outputs were regenerated for these provenance/UI fixes. No findings were deferred; Declined to judge was empty.

