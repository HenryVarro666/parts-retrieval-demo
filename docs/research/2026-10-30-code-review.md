# OCR, frozen Top-10 VLM and evidence workbench review

Reviewed the uncommitted `experiment/ocr-rerank-demo` changes against the approved spec and plan, including new untracked files. Review baseline: `edf35e8`. The required graph entry returned `missing_graph`; source inspection used the permitted fallback. No product files, environments or model inference were changed by this review.

## Findings

### 🟡 P2: Incomplete model objects can change the frozen ranking

Location: `partsid/rerank.py`, `validate_response` (original lines 36–42).

The original parser defaulted a missing `uncertain` field to `False` and accepted missing or incorrectly typed evidence fields. For example, `{"selected_id":"B"}` moved B ahead of A and returned `abstained=False`, despite retaining an invalid-response reason. This violated the malformed-output abstention contract.

Suggested fix/test: require an explicit boolean `uncertain` and the expected string evidence fields before accepting a selection. Test omitted fields, wrong types and explicit uncertainty, and verify that baseline order remains unchanged.

Resolution: the root implementer reported a RED → GREEN regression test and strict field validation fix during review.

### 🟡 P2: VLM cache identity omitted reference-image pixels

Location: `partsid/experiments.py`, request construction; `partsid/vlm_worker.py`, cached-response lookup (original lines 26–30).

The original cache identity covered query bytes, prompt text and generation limits, but omitted the contact sheet/reference pixels. Replacing a reference image without changing candidate metadata reused the old visual judgment and attributed it to the new input. A stubbed worker reproduction changed the reference image between invocations and observed one generation call rather than two.

Suggested fix/test: hash every actual visual input, including the generated contact sheet, and include those hashes in response matching and retained provenance. A reference-only pixel change must invalidate the cache.

Resolution: the root implementer reported adding all visual-input hashes and a regression test during review.

### 🟡 P2: Live uploads cannot display their retained OCR boxes

Location: `web/app.js:218` and `partsid/web.py:103`–`105` at review time.

`canShowEvidence` required `record.file` in live mode. The live API returned `Pipeline.run()` output without a dataset filename, so every successful upload disabled the OCR-view button and hid the boxes, even though its response contained complete view geometry and boxes. This prevented the requested evidence inspection for live input.

Suggested fix/test: produce the selected crop/rotation from the uploaded image locally in the browser, or return a bounded display image. Draw boxes only over the matching transformed pixels. Verify a rotated/cropped live result with no `file` property enables OCR view and aligns its overlay.

Resolution: the frontend implementer reported adding client-side data-URL cropping and counterclockwise rotation with matching box overlays. The root implementer owns actual browser/upload verification.

### 🟡 P2: The UI presents VLM stage sums as generic per-image latency

Location: `web/app.js:185`–`187`, `350`–`355`, and `417` at review time.

The page displayed VLM `ms.total` and its p50/p95 without showing `config.timing`. Those numbers sum cached baseline time and separately measured VLM generation, excluding model load; they are not one measured service invocation. Generic per-image/total labels made this materially different scope indistinguishable from OCR timing.

Suggested fix/test: display the saved timing scope beside VLM summary and per-sample latency, explicitly identifying the stage sum and excluded model load. Preserve the separate live-upload timing context.

Resolution: the frontend implementer reported adding the VLM stage-sum timing explanation to the summary and per-sample display. The root implementer owns browser verification.

### 🟡 P2: Duplicate JSON fields bypass uncertainty abstention

Location: `partsid/rerank.py`, `json.loads` in `validate_response`.

The parser accepted contradictory duplicate keys because Python retained the last value. For example, an otherwise complete object containing `"uncertain":true,"uncertain":false` returned `abstained=False` and accepted its selected ID. Contradictory selections or uncertainty should be treated as ambiguous output.

Suggested fix/test: reject duplicate object keys while parsing. Test repeated `selected_id` and contradictory `uncertain` keys, preserving raw output and the baseline order on abstention.

Resolution: the root implementer reported a RED → GREEN regression test and an `object_pairs_hook` parser that rejects duplicate fields. Their experiment-test run passed all 8 tests.

### Additional issue resolved by the root implementer

The root implementer identified that `--limit` smoke runs reused the full-run output filename. They reported separate `_smokeN` filenames and a regression test, preserving completed full-run artifacts.

## Verification and scope

- Focused tests passed at the initial review snapshot: `uv run --no-sync --extra experiments pytest -q tests/test_evidence_ocr.py tests/test_experiments.py tests/test_web.py` → 18 passed. Later fix-specific tests were reported by the root implementer, including 8 passing experiment tests after parser/cache/smoke fixes; the frontend implementer reported another passing syntax check after the UI fixes.
- All four measured OCR artifacts contained 44 unique query records. Recomputed metric summaries matched their saved values.
- All 11 original baseline, label and catalog hashes matched the preservation manifest.
- Dataset image-route EXIF normalization succeeded for every labeled image. Saved-view image and SVG geometry used matching contain/meet scaling.
- Inspected MLX-VLM 0.7.11's installed load/generate interfaces: the worker supplies actual image inputs and a pinned model revision. No ground-truth/review fields entered the VLM prompt or OCR view selector in the inspected paths.
- Displayed model, catalog and review text used `textContent`; external links were protocol-restricted. Frontend syntax passed `node --check`; referenced DOM IDs existed without duplicates.

Recommendation: **PASS for the source-review scope**, following the implementers' reported fixes for every finding. No unresolved consequential issue remains in this review. Fix-specific evidence is attributed above; this was not a second complete review of the revised diff. Actual VLM completion, final browser QA and a real live-upload inference are verified separately by the root implementer and are not certified by this source review. These results remain development evaluation with model-generated labels, not a blind test or expert gold standard.
