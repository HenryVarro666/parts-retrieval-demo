# OCR experiments and evidence demo implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Measure stronger OCR and constrained visual reranking, then expose the evidence in a local demo.

**Architecture:** Preserve the original Pipeline and baseline results. New evidence adapters feed the existing Pipeline; a separate experiment runner writes rich per-query JSON. A separate MLX worker exchanges JSON without importing MLX into the baseline environment. A loopback Python HTTP service serves a buildless HTML/JS workbench and lazy single-image inference.

**Tech Stack:** Python 3.12, existing PyTorch encoders, RapidOCR 3.10.0 and ONNX Runtime CPU, isolated mlx-vlm, stdlib HTTP, HTML/CSS/JS.

**Spec:** docs/superpowers/specs/2026-10-30-ocr-rerank-demo.md

## Global Constraints

- Preserve original labels, catalog and existing result files.
- All new inference runs use all 44 queries; subset experiments are labelled explicitly.
- Ground truth and review text never enter model prompts or view selection.
- Record model revisions/hashes and separate CPU/GPU and warm/cold timing.
- Local-only app; no external image uploads, training or paid inference.

## Review Focus

- A VLM invents a valid-looking identifier outside the frozen candidate set: reject and abstain.
- A VLM returns malformed JSON or uncertainty: retain baseline order and retain raw evidence.
- Multiple view hypotheses support different parts: record conflict, never silently report certainty.
- An image URL attempts traversal, or an upload is malformed/oversized: reject safely.
- An experiment fails partway: retain checkpointed records and do not label partial runs complete.

### Task 1: Review and repository research

**Files:** data/reviews/error_review_2026-10-30.json; docs/research/2026-10-30-error-review.md; docs/research/2026-10-30-github-ocr-survey.md

**Interfaces:** Produces traceable model-review records and primary-source implementation evidence. No changes to inference labels.

- [x] Review all 17 original images, mark ambiguous characters and label disagreements.
- [x] Verify schema completeness and source image existence. Expected: exactly 17 unique baseline errors.
- [x] Verify GitHub metadata and official architecture sources; select executable model versions.

### Task 2: OCR evidence adapters

**Files:** partsid/evidence_ocr.py; tests/test_evidence_ocr.py; pyproject.toml; uv.lock

**Interfaces:** `EvidenceOCR(name: str, device: str, parts: list[dict], multiview: bool=False)` exposes `read(path) -> str`, `name`, `last_result` (text, selected_view, views, conflicts), `metadata`. Views contain text and boxes in view coordinates plus crop/angle. Supports easyocr and rapidocr.

- [x] Write tests for deterministic geometry, strong-match view selection, conflicting aliases and empty OCR; run RED.
- [x] Implement evidence retention and fixed view policy without using query labels.
- [x] Install pinned optional OCR dependencies, run GREEN and one real-photo smoke.

### Task 3: Controlled experiments and visual reranking

**Files:** partsid/experiments.py; partsid/rerank.py; partsid/vlm_worker.py; experiments/vlm-requirements.txt; tests/test_experiments.py

**Interfaces:** Experiment JSON has `name`, `config`, `status`, `summary`, `records`; each record has file, gt, rankings, OCR evidence and timings. VLM worker consumes requests with query/reference images and public candidate fields; outputs raw response and parsed selected ID / observed text / reason / abstention. Ranking validation lives in `rerank.py` and never receives gt.

- [x] Write RED tests for candidate validation, abstention, hallucinated IDs, prompt leakage, paired metrics and candidate recall.
- [x] Implement checkpointed OCR runner and isolated VLM request/response worker.
- [x] Run four OCR combinations and baseline-Top10 VLM reranking on all 44 images. Expected: complete measured results; gains or losses are reported honestly.
- [x] Write paired comparison Markdown/JSON with model/cost/latency limits and review provenance.

### Task 4: Local evidence workbench

**Files:** partsid/web.py; web/index.html; web/app.js; web/style.css; tests/test_web.py; README.md

**Interfaces:** GET `/api/data` returns measured run/sample/catalog metadata, GET `/api/image?file=...` serves allowlisted images, POST `/api/predict` accepts a validated image and OCR choice and runs lazy local inference.

- [x] Write RED tests for path confinement, image validation and dataset/experiment joining.
- [x] Implement local HTTP service and responsive evidence workbench, with genuine live inference and labelled measured playback.
- [x] Run suite and browser QA: sample switching, run comparison, OCR evidence, candidates, review notes and upload.
- [x] Run fresh branch review, fix consequential findings, verify baseline hashes, document launch commands and measured results.
