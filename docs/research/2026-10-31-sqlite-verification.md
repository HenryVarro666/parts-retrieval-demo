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

The existing repository was verified private before sync: `HenryVarro666/parts-retrieval-demo`, default branch `main`. Only code, catalog/database, licensed dataset, experiment records, docs and the page are included. Virtual environments, model weights and local caches remain ignored. Fresh remote-clone verification is recorded below after the implementation push.
