# SQLite candidate pipeline implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans. Independent file ownership is explicit; root integrates and verifies before private sync.

**Goal:** Implement and measure OCR SQLite retrieval followed by shape and VLM candidate verification, and explain baseline metrics in the app.

**Architecture:** SQLiteCatalog is a stdlib search adapter; shape is a label-free pixel descriptor. A new CandidatePipeline uses the existing OCR/SigLIP and creates explainable candidate records. The experiment runner reuses the pinned isolated VLM worker with a new cache namespace and candidate set. The local page exposes the new live path and staged measurements.

**Tech Stack:** Existing Python3.12, sqlite3/FTS5, NumPy/OpenCV, RapidOCR, SigLIP and isolated MLX Qwen3-VL; existing HTML/CSS/JS.

**Spec:** docs/superpowers/specs/2026-10-31-sqlite-candidates.md

## Global constraints

- No query labels or review transcriptions in keyword extraction, search, shapes, prompts or decisions.
- Original JSON catalog/labels and measured result files remain unchanged.
- Preserve explicit candidate recall, missing/unknown evidence and abstention.
- No fitted weights/threshold sweeps; heuristic shape evidence cannot invent packages or pins.
- Fresh inference is distinguished from replay and timing projections; full44 comparisons.
- Existing private GitHub only, normal fast-forward updates; no cloud model calls or hosted publication.

## Review focus

- OCR punctuation/operator text must not inject SQL or FTS syntax; short numeric/date codes must not flood aliases.
- Duplicate keywords cannot multiply evidence; empty OCR requires explicit fallback rather than fake SQL hits.
- Nonuniform or edge-touching backgrounds must return unknown shape rather than false certainty.
- VLM input/caches must use the new pool, fingerprints and source pixels; no hidden old-pool/gt reuse.
- Live SQLite connections and mutable OCR state must be safe across serialized HTTP worker threads.

### Task 1: SQLite keyword search

**Owner/files:** worker, partsid/sqlite_catalog.py and tests/test_sqlite_catalog.py.

**Interface:** `build_catalog(parts: list[dict], db_path: Path, references: list[dict] | None=None) -> dict`; `SQLiteCatalog(db_path)`; `.search(ocr_text: str, limit: int=10, boxes: list[dict] | None=None) -> dict` with keywords, candidates[{part_id,score,tier,matches}], strong_ids, metadata. Each query opens/closes its own SQLite connection. Catalog source fingerprint retained. Parts data never gains query-derived aliases.

- [x] RED: exact/multiple/folded/noise/maker/empty/injection/duplicate and reopen/thread query behavior.
- [x] GREEN implementation, FTS5 and real temporary SQLite query tests.

### Task 2: Pixel shape evidence

**Owner/files:** worker, partsid/shape.py and tests/test_shape.py.

**Interface:** `describe_shape(path: Path) -> dict` (available, method, bbox, features, quality_notes); `compare_shapes(query: dict, reference: dict) -> float | None`. JSON-compatible, bounded cost, no labels/model downloads. Raw original-image coordinates; physical package and pin count remain unknown.

- [x] RED synthetic geometry invariance, foreground/no-foreground and unreliable-mask tests.
- [x] GREEN descriptor/quality implementation; one actual-photo smoke for errors only, no tuning.

### Task 3: Runtime and staged experiments

**Owner/files:** root, partsid/candidate_pipeline.py, partsid/candidate_experiments.py, tests/test_candidate_pipeline.py, data/catalog.sqlite, results/candidates/* and results/experiments/sqlite_*.json.

**Interface:** `CandidatePipeline.run(path) -> record` retains OCR evidence, sqlite search, candidate origins, shape evidence and rankings for sql/hybrid/shape. Runtime and runner share this implementation. A visual verification helper creates new-pool prompts/contact sheets and uses the pinned VLM worker.

- [x] RED pool caps/origins, strong-alias ordering, unknown-shape behavior, valid-pool VLM/abstention and metrics.
- [x] Implement, rebuild catalog, rerun OCR and all44 staged query records.
- [x] Fresh new-pool VLM inference on all44; compare all stages and old baselines.

### Task 4: Web, verification and private sync

**Owner/files:** worker web/app.js, web/index.html, web/style.css; root partsid/web.py, tests/test_web.py, README.md and verification docs.

- [x] Explain Top-1 baseline and Top-3; show keywords/database/shape/new candidate source and timing scope.
- [x] Expose SQLite+shape live mode and optional live VLM; validate actual upload end-to-end.
- [x] Independent source review, all tests, browser checks and preserved-input hashes.
- [x] Commit/push main and experiment branch; fresh remote clone DB/query/tests/web checks and final evidence.
