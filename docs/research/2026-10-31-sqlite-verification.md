# SQLite candidate pipeline verification, 2026-10-31

Scope: new OCR multikeyword SQLite/FTS5 retrieval, image supplements, conservative pixel-shape reranking, new-pool local VLM verification, staged evaluation, and the local evidence workbench. Review base: `d4cd746`; implementation branch: `experiment/sqlite-candidates`.

## Local verification

- `uv run --extra experiments pytest -q`: **133 passed in 2.91 s**.
- `node --check web/app.js` and `git diff --check`: passed.
- SQLite `PRAGMA integrity_check`: `ok`; the database includes catalog metadata, parts, aliases, makers, alias trigrams, reference images and FTS5 tables.
- All five complete result documents pass current-source fingerprint validation and contain exactly the 44 unique query files with unchanged labels.
- All **11** baseline SHA256 checksums match. All **239** data/result files previously tracked at `d4cd746` are byte-identical, including the catalog, labels, source photos and historical experiment/ensemble outputs.
- [Independent source review](2026-10-31-sqlite-code-review.md): **PASS** after fixes for empty-result presentation, full-query-set completion and source fingerprint validation. Additional targeted review verified unknown-shape badges and translated timing scope.

## Fresh evaluation and cache scope

All 44 queries were processed by the new RapidOCR/SQLite/image/shape pipeline. Shape evidence is available for 10/44 queries and 10/18 references. Top-1 is **36 / 38 / 38 / 42 / 41** for SQL-only / image-supplemented / shape / full VLM / gated projection. Full per-stage accuracy, recall and timings are in [the comparison](../../results/candidates/comparison.md).

The first new-pool VLM batch executed 44 forwards with new query/contact-sheet inputs and prompts. The final rebuild, following the provenance fixes and a fresh OCR run, reused these 44 same-pool responses only after validating prompt hashes, both VLM input images, pinned model revision and generation settings. Final runtime metadata correctly records 0 new and 44 validated cached generations. The reviewer independently checked these fingerprints and all saved decisions. Old EasyOCR candidate-pool judgments are not reused.

VLM times combine separately measured stage durations and exclude model loading. The 8/44 gate call count and its batch time are projections from the full verified batch. They do not measure a deployed selective service. No weights, shape thresholds or query-specific exceptions were fitted to these 44 labels.

The two full-VLM errors are candidate misses: UA741 `64573796.jpg` and ULN2003 `126915852.jpg`. The extra gate error is ATMEGA328P `149126951.jpg`, where a misread marking strongly matches another catalog alias. This identifies recall and false strong matches as remaining work.

## Browser and actual live inference

Verified through the actual in-app browser at `http://127.0.0.1:8765/`:

- Baseline help explains 27/44 = 61.4%, first-candidate correctness and the difference from individual confidence. The new full-VLM metric displays 42/44 = 95.5%.
- SQL-only empty results on ATMEGA328P `133222141.jpg` and I8086 `15625453.jpg` display an incorrect result and regression, rather than a missing record.
- Actual upload of NE555 `20729665.jpg`, RapidOCR multiview with optional verification enabled: SQL returns one candidate, shows keyword receipts and shape evidence, selects NE555 and **skips the VLM** under the strong gate. Service timing was **4.60 s**, including initial pipeline/model loading.
- Actual upload of 2N3055 `80876576.jpg`, same options: OCR reads `9 719`, SQL returns zero candidates and the image pool supplies ten; shape is unavailable. The service **executes the local VLM**, returns 2N3055 and displays its raw decision. Service timing was **9.99 s**, including the required visual process/model loading. This verifies the conditional path on real requests, not the projected batch latency.
- After the badge fix, the same saved unavailable-shape sample shows no shape-evidence badge. Displayed input timing uses the translated scope note. Browser error/warning logs are empty.
- The default narrow browser viewport shows the stacked input/workbench layout. [Saved screenshot](../screenshots/sqlite-workbench-2026-10-31.jpg) captures the original baseline, new result and explanatory help.

These are local M4 Pro checks. The dataset is small and has model-generated labels; results do not establish independent-test accuracy or behavior on another GPU architecture.

## Private GitHub continuation

The existing repository was verified private before sync: `HenryVarro666/parts-retrieval-demo`, default branch `main`. Only code, catalog/database, licensed dataset, experiment records, docs and the page are included. Virtual environments, model weights and local caches remain ignored.

Implementation commit **`b0f2d7055ff7eba45baeccd68a70b92903081377`** was atomically pushed by normal fast-forward to both `main` and `experiment/sqlite-candidates`. A new clone of remote `main` at `/tmp/partsid-sqlite-verify-b0f2d70` verified:

- `uv sync --frozen --extra experiments`: succeeded, creating a new Python 3.12.13 environment from the lockfile. Available package/model download caches on this Mac were reused; this was not an uncached network-install or another operating-system test.
- `uv run --frozen --extra experiments pytest -q`: **133 passed in 17.31 s**.
- Tracked SQLite integrity, multiple strong keywords, noise-only no-candidate behavior, and a rebuild into a separate temporary DB: passed. Actual search results matched across SQLite 3.53.1 (tracked DB metadata) and 3.53.4 (system Python rebuilding); version metadata was correctly allowed to differ.
- Current-source hashes and exact 44-query alignment for all five result files, and the 11 original baseline checksums: passed.
- JavaScript syntax and fresh server on port 8766: passed. HTML/JS/CSS and `/api/data` returned successfully with 44 samples, 18 parts and all five new stages.
- Actual fresh-clone upload through `/api/predict` ran RapidOCR, SQLite and shape, selected NE555, and skipped VLM with both `used_vlm=false` and `actual_vlm_executed=false`. Service time was 4.845 s including initial model/pipeline loading. The response carried neither a query ground truth nor a dataset filename. The clone has no copied `.venv-vlm`; this smoke validates the no-VLM gate path. The weak-evidence actual VLM path was separately verified in the original working directory as described above.
- The temporary port-8766 server was terminated. The user's local workbench remains available on port 8765. No full 44-query model run was repeated in the clone; the real clone inference smoke and all saved-result/source checks are distinguished above.

The final follow-up commit only records this verification and completes the plan checklist; it does not change executable code or measured outputs.
