# Multi-image identification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify one component from 1–3 photos, explain each photo, compare first-photo and fused runs, and ship reproducible private artifacts.

**Architecture:** A focused multi-image module wraps the existing single-image pipeline. The loopback API supplies paired independent runs; the existing three-language UI shows per-photo evidence and fused candidates. A separate manifest-based evaluator keeps real paired data distinct from duplicate controls.

**Tech Stack:** Python / Pillow / SQLite / existing local OCR, SigLIP and MLX VLM; plain JS / CSS.

**Spec:** `docs/superpowers/specs/2026-10-31-multi-image.md`

## Global constraints

- 1–3 images, each ≤10 MB /16 MP; total ≤48 MP. No cloud APIs or hosted publication.
- No label/review/query-name leakage; frozen Top-10 candidate constraints and existing catalog unchanged.
- Preserve all old data/results and single-image behavior; raw OCR / component IDs stay original in all three languages.
- Real paired accuracy requires same-physical-object grouping; duplicate controls never imply real-angle improvement.
- Two measured paths share loaded retrieval models, not extracted query records or live VLM outputs; setup and request timing are separate.

## Review focus

- Conflicting strong identifiers and different objects must not silently pass the gate (Task 1).
- Exact/near duplicate photos must not fabricate independent consensus (Task 1).
- Invalid third image or unsupported legacy multi-image input must reject before model work (Task 2).
- Switching photo/language or late translation must keep the correct geometry, OCR and fused result (Task 2).
- Unverified groups, missing/stale pixels or duplicate files cannot be reported as true multi-angle accuracy (Task 3).

### Task 1: Multi-image fusion and paired runtime

**Files:** Create `partsid/multi_image.py`, `tests/test_multi_image.py`.

**Interfaces:** `run_group(pipeline, paths, verify_visual=False, namespace=None) -> record`; `compare_paths(pipeline, paths, verify_visual=False, namespace=None) -> {record, baseline_record, comparison}`. Per-photo evidence lives in `record.photos`; aggregate rankings remain compatible with the workbench.

- [x] Write and run failing behavior tests for candidate recovery by complementary evidence, conflict-aware gate, duplicate invariance, near-duplicate group weights and independent paired execution.
- [x] Implement pixel fingerprints, deterministic group-normalized RRF, merged SQL receipts / origins / support, constrained joint VLM preparation, and measured paired runtime.
- [x] Verify prompt/image hashes cover all inputs, no labels enter prompts, single-image unchanged, abstention preserves fused order; run focused tests and commit.

### Task 2: Upload API and three-language evidence UI

**Files:** Modify `partsid/web.py`, `web/index.html`, `web/app.js`, `web/i18n.js`, `web/style.css`; extend `tests/test_web.py`, `tests/web_i18n.test.cjs`.

**Interfaces:** `/api/predict` accepts legacy `image` or new `images` (mutually exclusive). Multiple images require SQLite. Response adds baseline / comparison and per-photo records. Optional label stays client-only.

- [x] Write and observe failing tests for 0/4 images, malformed third image, both payload forms, oversized aggregate, and multi-image legacy rejection before model startup.
- [x] Add atomic multi-file selection, photo navigation / OCR geometry, per-photo evidence, fused support and paired candidate/time display; local optional scoring and three-language strings.
- [x] Test UI consumer behavior and existing saved-record replay, then verify in the actual local browser; commit.

### Task 3: Reproducible experiments and delivery

**Files:** Create `partsid/multi_image_experiments.py`, `tests/test_multi_image_experiments.py`, `results/multi_image/*`, docs; update README and beginner guide.

**Interfaces:** CLI `python -m partsid.multi_image_experiments control` runs 44 duplicate controls; `run MANIFEST` validates and runs real paired triplets. `report` regenerates a standalone comparison. API includes separate multi-image experiment status/report.

- [x] Write and run failing tests for manifest identity, grouping provenance, image hashes, no catalog-query overlap, missing/stale sources and duplicate-file rejection for real pairs.
- [x] Implement complete-run / source-pixel validation and metric report with explicit data scope; run available real pairs or honestly record zero, plus control and local joint-VLM smoke experiments.
- [x] Run Python / Node tests, browser checks and independent whole-branch review; fix substantive findings with reproducing tests. Verify all pre-existing data hashes remain unchanged.
- [x] Commit and push to the existing private repository, then validate fresh-clone setup, tests, report replay and private remote refs. Record limitations and deliver browser.

Delivery evidence: implementation and fixes pushed as `350cf33`; private GitHub `main` and `feature/multi-image-fusion` match. Fresh remote clone `/tmp/partsid-multi-verify-350cf33` passed frozen installation, 169 Python /15 Node tests, fixture/report/360-entry translation replay with a clean tree and no `.venv-vlm`. Final documentation-only delivery update records the same verified code.
