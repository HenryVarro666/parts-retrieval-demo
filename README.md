# parts-retrieval-demo

Identify an electronic part from a photo using OCR keywords, SQLite catalog search, image and shape evidence, and optional visual-model verification. Compare each stage with the original three-channel baseline on a small labelled set.

This is a small demo built from public photos and off-the-shelf models. Nothing is trained or fine-tuned. Given a photo of a chip or module, it returns a ranked list of catalog parts.

Claude Code (Anthropic's AI coding agent) produced the original baseline and photo labels on 2026-10-30 (see Data). The subsequent OCR/VLM experiments and local evidence workbench are documented separately below; the original catalog, labels and result files are preserved.

## Evidence workbench and follow-up experiments

Launch the local page (Apple Silicon and CPU OCR path tested):

```bash
uv sync --extra experiments
uv run --extra experiments python -I -m partsid.web --port 8765
```

Open <http://127.0.0.1:8765>. Preset photos replay saved experiment records; image upload runs real local inference. The default upload path uses SQLite keyword retrieval, image supplements and shape reranking. Enable the optional visual verification checkbox to run the local VLM only when the fixed strong-identifier gate does not accept the OCR result. This requires the separate Apple Silicon VLM environment described below. The original retrieval path remains selectable.

Use the top-right language selector for **中文 / English / Español**. The interface switches immediately and remembers the choice in this browser; Chinese is the initial default. Changing language preserves the selected sample, experiment and any running/uploaded image, without rerunning inference. UI labels, catalog display names, system explanations and accessibility text are localized; raw OCR text, model-generated explanations, review prose, identifiers and experiment values retain their source content. No translation service or additional runtime dependency is used. Language behavior tests: `node --test tests/web_i18n.test.cjs` (Node is only needed for these tests).

The page shows the selected OCR view, text boxes, keyword matches and database fields, candidate origins, shape availability, reference images, model decisions, timings and before/after metrics. **Baseline Top-1** means the original method's first-ranked part is correct: **27/44 = 61.4%**. Top-3 means the correct part occurs among its first three candidates. These are dataset metrics; individual model scores are not calibrated probabilities. Uploads are processed locally in temporary files and are not saved to the dataset.

## SQLite keyword retrieval and candidate verification (2026-10-31)

The new flow is `photo → multiview RapidOCR → SQLite keywords → image supplements → shape reranking → optional VLM`. The [complete stage comparison](results/candidates/comparison.md) and per-query `results/experiments/sqlite_*.json` distinguish database recall from downstream reranking:

| Method | Top-1 | Top-3 | Recall@10 |
|---|---|---|---|
| Original EasyOCR baseline | 27/44 (61.4%) | 33/44 | 43/44 |
| Existing RapidOCR multiview | 38/44 (86.4%) | 40/44 | 42/44 |
| SQLite keywords alone | 36/44 (81.8%) | 36/44 | 36/44 |
| SQLite + image supplements | 38/44 (86.4%) | 39/44 | 42/44 |
| Above + shape reranking | 38/44 (86.4%) | 40/44 | 42/44 |
| New candidate pool + VLM on every query | **42/44 (95.5%)** | 42/44 | 42/44 |
| Strong SQL identifier first, otherwise VLM | 41/44 (93.2%) | 42/44 | 42/44 |

`data/catalog.sqlite` is a real, tracked SQLite/FTS5 database containing the 18 public catalog parts, aliases, makers, descriptions and reference-image paths. Exact and glyph-folded aliases take priority; indexed trigrams tolerate partial OCR errors, and FTS5 supports descriptive keywords. SQL is parameterized, repeated terms are deduplicated, and same-view adjacent words can form a split identifier. Empty/noise OCR produces no SQL candidates. Every match records its term, catalog field and match rule. No query-derived aliases were added.

The candidate pool protects strong SQL identifiers, combines the SQL top five with the SigLIP appearance top five, deduplicates and fills to at most ten. Image additions retain their own origin. Shape uses a conservative foreground mask and three pixel descriptors: elongation, solidity and circularity. Unreliable masks return unknown. Shape was available for only **10/44 query photos** and **10/18 references**; it improved Top-3 by one without improving Top-1. It does not estimate physical dimensions, package names or pin count, and it cannot exclude the same part in another package.

The pinned Qwen3-VL model receives the query, a shuffled reference contact sheet, public candidate fields and explicitly heuristic shape evidence. It can select only an existing candidate or abstain. This new-pool evaluation reached 42/44; both remaining failures lack the correct part in the ten-candidate pool: UA741 `64573796.jpg` reads `741P 8414` without a supported strong alias, and ULN2003 `126915852.jpg` has empty OCR. The gate projects only **8/44** VLM calls and reaches 41/44. Its extra error is an OCR misread that happens to be another valid catalog alias, so accepting a strong match early has an accuracy cost. No exception was fitted to that query.

All 44 OCR/SQLite/image/shape records were freshly measured. The first new-pool VLM pass generated 44 responses. After provenance checks were strengthened and OCR rerun, the final result rebuild reused those 44 responses only after validating each prompt, both VLM input images, model revision and settings. Its metadata therefore records **0 new / 44 validated cached generations** for the final rebuild. The new namespace never reuses old EasyOCR candidate-pool judgments. VLM latency is a sum of separately measured stages, excluding model loading; the gate row is a policy projection from that complete batch. Live uploads implement actual conditional calls, but the batch gate latency is not a measured service throughput result.

Rebuild and evaluate the new stages:

```bash
# Database construction/comparison use standard Python; inference needs the extras.
python3 -m partsid.candidate_experiments build
uv run --extra experiments python -I -m partsid.candidate_experiments run
# Requires .venv-vlm below; uses new-pool cache fingerprints.
uv run --extra experiments python -I -m partsid.candidate_experiments vlm
python3 -m partsid.candidate_experiments compare
uv run --extra experiments pytest -q
```

`run` replaces only the new SQLite-stage files. Complete runs require all 44 unique queries with matching labels; partial checkpoints cannot enter the comparison. Source hashes cover the catalog, database, labels, query pixels, reference manifest and reference pixels. If those change, rebuild and rerun before visual verification or comparison. Saved playback needs no model downloads; the VLM environment and model caches remain excluded from Git. This is still the same small development set with model-generated labels, not an independent blind test.

## Previous OCR and frozen-pool experiments

The [paired model comparison](results/experiments/comparison.md) reports all 44 queries, gains and regressions. New JSON records retain OCR geometry, competing views, model hashes and raw VLM decisions. The original EasyOCR whole-image result reproduced 27/44. RapidOCR whole-image obtained 35/44; its eight-view variant obtained 38/44. Frozen-baseline Top-10 Qwen-VL reranking obtained 39/44 with 3 abstentions (13 gains, 1 regression); its median generation-plus-cached-baseline stage sum was about 5.8 s, versus 0.75 s for RapidOCR views. These are results on the same development set, not an independent blind test or production accuracy claim.

## Voting and selective OCR/VLM combinations

Five fixed rules were replayed against the saved outputs of all 44 queries, without rerunning models or tuning weights. [Full combination comparison](results/ensembles/comparison.md):

| Combination | Top-1 | Wins / regressions versus RapidOCR views | VLM calls required by rule |
|---|---|---|---|
| Five equal votes (correlated OCR variants included) | 37/44 | 2 / 3 | 44/44 |
| One representative per model family | 39/44 | 1 / 0 | 44/44 |
| OCR rankings + VLM singleton, RRF | 38/44 | 2 / 2 | 44/44 |
| Strong, unconflicted OCR first; otherwise VLM | **40/44** | **2 / 0** | **8/44** |
| Two OCR pipelines agree; otherwise VLM | 39/44 | 3 / 2 | 17/44 |

The strongest development result accepts the new OCR only when one exact/glyph-folded catalog identifier agrees with its fused Top-1 and no cross-view strong-ID conflict exists. Otherwise it consults the VLM's existing frozen-baseline Top-10 decision, falling back to the new OCR on abstention. The >=0.9 gate is an alias-match score, not a calibrated OCR probability. Simple voting can amplify correlated errors; the results do not establish that adding voters always helps.

Reproduce the combination comparison with **standard Python only**, no GPU, model downloads or optional dependencies:

```bash
python3 -m partsid.ensemble
```

These earlier combinations are offline policy replay from actual saved outputs. Stage-sum costs are estimates from the required complete OCR branches and any VLM generation, exclude model loading, and are not new end-to-end measurements. The web page labels these runs as combination replay and shows branch votes/call decisions. The fixed policies and input SHA256 values are saved with the results. The newer SQLite live path separately supports conditional VLM verification.

For another machine, clone the private repository's default `main` branch, then launch the same page:

```bash
git clone https://github.com/HenryVarro666/parts-retrieval-demo.git
cd parts-retrieval-demo
uv sync --frozen --extra experiments
uv run --extra experiments python -I -m partsid.web --port 8765
```

Repository access requires your GitHub credentials. The dataset, code, measured results and page are tracked; environments and model caches are excluded. Saved-result replay works without downloading models. Real OCR inference downloads the pinned OCR/encoder artifacts as needed. The local VLM re-inference path below is specific to Apple Silicon; other machines can still replay all recorded VLM and combination results. NVIDIA OCR/encoder setup is described later and remains unverified on an NVIDIA machine.

## Model reproduction details

- [Review of the 17 original errors](docs/research/2026-10-30-error-review.md): 16 readable primary markings and one uncertain small image, from a non-blind model visual review, not expert gold. Old labels and aliases were not patched.
- [GitHub OCR survey](docs/research/2026-10-30-github-ocr-survey.md): repository stars, architecture, official sources and license scope, captured on 2026-10-30.
- [Integration notes](docs/research/2026-10-30-integration-notes.md): actual model routes and image input conventions.

Reproduce the four OCR conditions (new files under `results/experiments/`):

```bash
uv run --extra experiments python -I -m partsid.experiments ocr --engine all
uv run --extra experiments python -I -m partsid.experiments compare
uv run --extra experiments pytest -q
```

The views condition evaluates whole image and a fixed central crop, each at four right-angle rotations, and chooses a hypothesis using only public catalog aliases and OCR scores. This groups view generation and catalog-guided selection into one ablation; it does not isolate each operation. Complete OCR runs are reused by name; remove only the specific new experiment JSON if you intend to rerun it. `--limit N` produces separately named smoke results, never a complete benchmark.

The local visual reranker uses a separate **macOS Apple Silicon** environment to preserve the baseline environment:

```bash
uv venv .venv-vlm --python 3.12
uv pip install --python .venv-vlm/bin/python -r experiments/vlm-lock.txt
uv run --extra experiments python -I -m partsid.experiments vlm
uv run --extra experiments python -I -m partsid.experiments compare
```

It downloads the pinned `mlx-community/Qwen3-VL-4B-Instruct-4bit` snapshot (about 3.1 GB). Each query is compared against its frozen baseline Top-10 using query pixels, shuffled public candidate fields and a reference contact sheet. Query ground truth, file names and review transcriptions are excluded from the prompt. Invalid, out-of-set or uncertain decisions retain the baseline order. VLM raw outputs are checkpointed under ignored `data/cache/vlm/`; cache keys include both image inputs, the prompt, model revision and generation settings. VLM timings sum cached baseline stage time and separately measured generation, exclude model load, and are not one measured end-to-end request. CUDA VLM execution has not been implemented or tested.

## Original baseline pipeline

```
photo ──► OCR (EasyOCR | Tesseract) ──► OCR text ──┬──► identifier channel: part-number match against catalog aliases
                                                   └──► text channel: BGE-small embedding vs. catalog part documents
photo ──► SigLIP image embedding ──────────────────────► image channel: cosine vs. catalog reference photos

identifier + text + image rankings ──► reciprocal rank fusion (k=60) ──► ranked list of catalog parts
```

| Piece | Choice | Why |
|---|---|---|
| OCR | EasyOCR (CRAFT + CRNN, PyTorch); Tesseract as baseline | Scene-text OCR copes better with laser-etched chip markings than page OCR; the eval shows by how much |
| Identifier channel | Whole-alias match in the OCR words, the same match after an OCR glyph fold (O and Q to 0, I and L to 1, S to 5, B to 8), and as a fallback trigram similarity computed like PostgreSQL `pg_trgm` `similarity()` (rules below) | Part numbers are the strongest signal when they are readable; the fold and the trigram fallback tolerate OCR errors |
| Text channel | `BAAI/bge-small-en-v1.5`, CLS pooling, catalog documents = name + part numbers + makers + description; skipped when OCR finds no token of 3 or more letters or digits | Catches partial reads and maker names |
| Image channel | `google/siglip-base-patch16-224` image tower, best match over a part's reference photos | Works when no text is legible at all |
| Fusion | Reciprocal rank fusion, k=60, top-10 per channel, equal weights. The identifier channel passes only its exact or glyph-folded hits (score 0.9 or more) when it has any, and its trigram hits otherwise | Standard and parameter-light, not tuned on the eval set; a clean part-number read is not outvoted by its own trigram neighbours |
| Vector search | numpy brute force | 18 parts; at catalog scale this is `pgvector` (`ORDER BY embedding <=> $1`) |

Identifier rules. The OCR text is split into words, and each pair of adjacent words is also joined into one, because OCR splits markings; in the rules below, a word can also be such a joined pair. An alias found inside a word scores 1.0, and one found after the glyph fold on both sides scores 0.9, except that an alias made only of digits needs a real digit in the matched text (`SSS` is not read as `555`). Aliases shorter than 4 characters (`555`, `741`, `317`, `286`, `Z80`) count only when a word equals them, never inside a longer word. An alias with 6 or more letters and digits, hyphens not counted, may also match exactly or folded across three adjacent words (`ESP-12F` can, `ESP-01` cannot). Otherwise the score is the `pg_trgm` similarity, computed only when the alias and the word both have 4 or more characters, the word contains a digit, and the word either starts with a letter or keeps a letter after look-alike letters are read as digits, which rules out date codes such as `741O`. A part is listed when its best score is 0.35 or more.

## Data

- `data/parts.json`: 18 catalog parts, each with a name, part-number aliases, makers, a one-line description and the Wikimedia Commons categories its photos come from. The set includes confusable groups (Intel 8080 / 8085 / 8086 / 8088 / 80286, ATmega8 / ATmega328P, 7805 / LM317, ESP8266 / ESP32, 555 / 741).
- Photos (`partsid/fetch_commons.py`): per part, the first 16 JPEG files by Commons page id in the part's own category, plus up to 16 more from part-number subcategories listed by hand in `parts.json` (91 subcategories for 11 of the 18 parts, such as "Intel D8086"; never computers, boards or second sources). Files whose titles contain a keyword such as die or schematic are skipped while listing, before the 16 are taken. The keyword list is short and English. It misses titles in other languages and keywords inside longer words ("ESP32-Dieshot"). It also misses titles that use an English word not on the list: the three scanned ads came through as "Ad" and "Advertisement", and opened packages as, for example, "case opened" or "Disassembled". Titles that do not say what the image shows get through too. About 40 downloads were therefore pictures of a die (23, five of them in an opened package) or drawings and scanned ads; curation dropped all of them. On 2026-10-30 this rule selected 322 files. A first download pass got 170 and a slower second pass 39 more; Commons refused the other 113 both times (HTTP 429), and they were not requested again. So the dataset is the 209 that downloaded, and the losses are uneven: the Intel 8080 to 80286 parts got 51 of their 106 files. Photos are stored upright and at most 960 px wide under `data/images/raw/`, and they are in this repository; each keeps its own Commons license. For each of the 209, `data/manifest.csv` records the Commons page with its license and author (Commons metadata names no author for 5), and the URL the file was fetched from. That URL was not recorded for one file, query NE555 22764784. Its JPEG quantization tables match the ones all 96 Commons thumbnails in the dataset share, not the ones of the 61 files shrunk locally, so it is most likely the 960 px thumbnail. The manifest, not the rule, defines the dataset: `--from-manifest` fetches each file from its recorded URL (for NE555 22764784, today's 960 px thumbnail, or its original shrunk locally if Commons refuses the thumbnail) and accepts only a file of the recorded size.
- `data/curation.csv`: one row per downloaded photo. The labels come from Claude vision subagents, not from a domain expert. Two labellers judged every photo independently, the second seeing them in reverse order, under fixed written rules:
  - keep a photo only if it is a photograph whose main subject is this part, sold under this part number (clones and second sources sold under another number are dropped, and so are boards where the part is one chip among many);
  - say whether the part number is legible in the stored image, and copy what it reads;
  - group kept photos that show the same physical unit or come from the same photo session.

  Disagreements on keep or legibility went to a third labeller. A group is the union of both labellers' groupings, carried across rounds. A photo was labelled again whenever its stored size changed (23 photos first stored at a smaller size were later downloaded at full size); `judged_size` records the size each label was made on. Two NE555 files were downloaded again at the same size and not labelled again. One of them, query 20729665, is the same picture re-encoded, and its marking `NE555N` reads the same. The two labellers agreed on keep for 121/122, 100/100 and 10/10 photos in the three rounds, and the tie-break was needed twice. 91 of the 209 photos were kept. The full rules and agreement table are in `data/curation_rules.md`.
- `data/labels.csv` is generated from the curation by a fixed rule (`partsid/make_labels.py`). Per part, the kept photos are sorted by Commons page id. The first is the catalog reference. The queries are the next photos from sessions not yet used (never the reference's session, at most one per session), up to 3 per part. Nobody chose which photo plays which role. A file the manifest lists under two or more catalog parts (a museum case of Intel CPUs, for example) is excluded. Five files are listed that way, so the 209 downloads are 203 distinct files; curation had dropped all five anyway, so the rule changes no label.
- Result: 18 reference photos, one per part, and 44 query photos covering all 18 parts (43 with a legible part number). Seven parts have one or two queries, because their kept photos come from fewer than four separate sessions. For three of them (I8080, I8085, I8086) Commons refused half or more of the files the rule selected.

## Run it

```bash
uv sync                                                    # Python 3.12 venv (see .python-version) with torch, transformers, easyocr
uv run python -I -m partsid.make_labels                    # data/curation.csv -> data/labels.csv
uv run python -I -m partsid.evaluate --ocr easyocr
uv run python -I -m partsid.evaluate --ocr easyocr+rot     # EasyOCR also tries 90/180/270 degree rotations
uv run python -I -m partsid.evaluate --ocr tesseract       # needs the tesseract binary (brew / apt)
uv run pytest -q
```

The photos come with the repository, so a clone needs no download from Commons. To rebuild them from Commons instead, delete `data/images/raw/` first, then run `uv run python -I -m partsid.fetch_commons --from-manifest` (needs curl and network; allow 10+ minutes). With the photos in place it only checks them against the manifest and downloads nothing.

`uv run python -I -m partsid.contact_sheet` tiles each part's photos into one image for checking the curation by eye.

The device is picked automatically: `cuda`, then Apple `mps`, then `cpu`; override with `--device`.

Notes for a rerun:

- When rebuilding the photos, `fetch_commons` does not wait out or retry a refused download within a run. A file that Commons refuses (HTTP 429) or that fails to download is reported as not fetched, and the run exits with status 1. Run the same command again; it fetches only what is still missing.
- `evaluate` reads only the 62 photos in `data/labels.csv` (18 references, 44 queries) and stops if one is missing; the other 147 are used by `contact_sheet` only. Its first run downloads the SigLIP and BGE weights from Hugging Face and EasyOCR's two model files. Each run overwrites `results/<ocr>.md`, `.json` and `_per_query.csv`; add `--run-name NAME` to write `results/NAME.*` instead.
- A second run on the same Mac with the same files reproduced every row of each `results/<run>_per_query.csv` except the timings. Other machines have not been compared, so no tolerance is claimed; diff the per-query CSVs to see what moved.
- The photos in the repository are the files that were evaluated. A rebuild from Commons checks each file's pixel size, not its bytes, and the manifest records no checksums, so a rebuilt photo can differ from the one evaluated without any warning. Of the 62 photos `evaluate` reads, 17 were shrunk locally from larger originals, which another Pillow version may resample a little differently, and 25 are Commons thumbnails, which Commons renders on demand and may render again. A newer upload of any file would also be accepted if it comes out at the recorded size, and NE555 22764784 has no recorded URL (see Data).
- `uv.lock` pins the Python packages, and with them EasyOCR's two model files, which easyocr checks by MD5. `partsid/embed.py` pins the two Hugging Face models to the revisions these results used (SigLIP `7fd15f0`, BGE `5c38ec7`; each report lists them); another `--image-model` or `--text-model` loads that model's current main revision. Nothing pins the tesseract binary: the Tesseract column was measured with tesseract 5.5.4 from Homebrew.

### On an NVIDIA RTX 50-series GPU (e.g. 5080)

Blackwell cards need a PyTorch build for CUDA 12.8 or newer. `pyproject.toml` routes torch and torchvision to the `cu132` PyTorch index on Linux and Windows (macOS keeps the PyPI wheels), so the commands are the same; the NVIDIA driver must be recent enough for CUDA 13.2. This path has not been run on an NVIDIA GPU, and every number below is from the Mac.

```bash
uv sync
uv run python -c "import torch; print(torch.cuda.get_device_name(0))"
uv run python -I -m partsid.evaluate --ocr easyocr --device cuda --run-name easyocr_cuda
```

`--run-name` writes `results/easyocr_cuda.*` and leaves the Mac results in place.

`--image-model` also accepts a larger image tower such as `google/siglip-so400m-patch14-384`. It has not been tried here; add `--run-name` so the run does not overwrite `results/easyocr.*`.

## Results

Measured on 2026-10-30 on an Apple M4 Pro, over the 44 query photos. The full report of each run is in `results/` (`easyocr.md`, `easyocr+rot.md`, `tesseract.md`, each with a `.json` summary and a `_per_query.csv`): intervals, paired tests, a per-part table, look-alike families and every miss.

Top-1 accuracy, the share of photos whose first answer is the right part:

| Channel | EasyOCR | EasyOCR, rotations tried | Tesseract |
|---|---|---|---|
| identifier: part number read by OCR | 18/44 (41%) | 11/44 (25%) | 2/44 (5%) |
| text: embedding of the OCR text | 13/44 (30%) | 15/44 (34%) | 2/44 (5%) |
| image: SigLIP, no OCR | 17/44 (39%) | 17/44 (39%) | 17/44 (39%) |
| fused: the pipeline | 27/44 (61%) | 25/44 (57%) | 19/44 (43%) |
| fused without the text channel (ablation) | 28/44 (64%) | 22/44 (50%) | 17/44 (39%) |

Picking a part at random gets 1 in 18 (6%). The 95% Wilson interval for 27/44 is 47% to 74%. The EasyOCR pipeline has the right part in its top 3 for 33 of the 44 photos (75%).

What the numbers show:

- The identifier channel is precise but often silent. With EasyOCR it named a part on 18 photos and was right on all 18. 17 of them are exact or glyph-folded reads, the count used for "read the right part number" below; the 18th is a trigram match on the misread `ATMEG4828P`. On the other 26 photos it found nothing: 23 where OCR did not get the part number right, one with no legible marking, and two whose markings the catalog does not cover. Those two, `P80C88A-2` (the CMOS version of the 8088) and `741P`, contain no alias the identifier accepts (`741` never counts inside a longer word): a perfect read of the first would match nothing, and of the second only weakly (trigram score 0.375 against the 741's alias `741CN`). The alias lists were left as they were rather than patched after seeing the misses.
- The image channel alone has the right part first for 17 photos and in its top 3 for 27. It cannot tell the Intel CPUs apart: of the 11 photos of Intel 8080 to 80286 parts it got 3 right, and all 8 wrong answers named another Intel part. The ULN2003 reference photo is the closest match for 6 photos of other parts. All six are close-ups of parts on circuit boards, and that reference shows its chip in a socket on a driver board, so the channel seems to match the board more than the part; the one ULN2003 query, a loose chip on white, ranks that reference 11th.
- Fusion is where the channels pay off. The pipeline is right where the image channel is wrong on 15 photos, and the reverse happens on 5 (sign test p = 0.04). Counted per part, so that three photos of one part do not count three times, it is better on 11 parts and worse on 4 (p = 0.12). Photos of different parts share photographers, so even the per-part count is not fully independent (see Limits).
- The text channel did not earn its place. Without it (last row of the table) the EasyOCR pipeline gets one more photo right, while the rotation and Tesseract pipelines get 3 and 2 fewer; no difference reaches significance (sign test p of 0.5 or more). When OCR returns junk, the text embedding still ranks all 18 parts, and fusion weighs that ranking like the image channel's. It stays in the pipeline because removing it after seeing these numbers would tune the system to the test set. Gating it on OCR quality is the next thing to try, on new photos.
- Trying rotations hurt. With 90, 180 and 270 degree rotations EasyOCR read the right part number on 10 photos instead of 17: it keeps whichever orientation scores highest, and some upright markings score higher upside down ("8080" came back as "0808"). It is also slower: 185 ms per photo at the median and 605 ms at the 95th percentile, against 128 and 239 ms without rotations.
- Tesseract read the part number on 2 of the 44 photos, so its pipeline is close to the image channel alone.

Latency per photo with EasyOCR, warm (second pass over the same photos), in milliseconds:

| Stage | p50 | p95 |
|---|---|---|
| OCR | 108 | 212 |
| identifier match | 1 | 3 |
| text embedding (38 of 44 photos; skipped when OCR finds no token of 3 or more letters or digits) | 5 | 5 |
| image embedding and search | 16 | 18 |
| fusion | 0 | 0 |
| total | 128 | 239 |

OCR takes most of the time. The first pass over the same photos averaged 185 ms per photo, which includes one-time warm-up for each new image size, and loading the three models took 3 s with the weights already on disk. With Tesseract the median total was 124 ms. All of these numbers come from one Apple M4 Pro: the neural networks ran on its GPU through `mps`, and Tesseract and the rest of the pipeline (OCR post-processing, identifier match, numpy search, fusion) on its CPU. The CUDA setup for an RTX 5080 (see above) has not been run.

## Limits

- Small, and the photos are not independent. With 44 query photos one more right answer moves top-1 by 2 points. Photos of one part are related, and 23 of the 44 queries come from six photographers who each have queries of two or more parts: one has 7 queries of 5 parts, another 6 queries of 6 parts from one series of uploads, mostly on the same orange backdrop. Those two account for 8 of the 15 photos where the EasyOCR pipeline beats the image channel. So the intervals above are if anything too narrow, and the p values too small.
- Mostly easy photos. Most queries are clean shots of a loose part, and 43 of the 44 show a legible part number. Ten are close-ups of a part soldered or socketed on the board of a device or development board, 7 of them by one photographer. On those ten the image channel was right once, against 16 of the other 34 (Fisher exact p = 0.06), while the identifier channel was right on 5, against 13 of the 34. The split was made after seeing the results, and it is sensitive: counting also the ESP-12 modules on breakout adapters (ESP8266 54458803) gives 2 of 11 against 15 of 33 (p = 0.16). Field photos, with dust, glare, odd angles and labels partly hidden, are likely to be harder for both channels.
- Labels by an LLM. Two independent Claude vision passes and a tie-break, under the rules in `data/curation_rules.md`. The passes agreed closely, but no domain expert has checked the labels.
- A toy catalog. 18 parts with one reference photo each. A real parts catalog has thousands of entries, many in identical packages, so the image channel would face far more look-alikes than the Intel family here.
- Two aliases came from the data. `Z08400` (Zilog's ordering code for the NMOS Z80) was added while the photos were being curated, before any evaluation run; `ESP-WROOM-02` (Espressif's module name) was added after a code review spotted it on a dataset photo. Both are real part numbers. Aliases also go into the part documents the text channel embeds, so an alias can move results even where OCR never reads it. Without `Z08400` the rotation run would miss Z80 photo 6975899 in three rows of the table (identifier 10, pipeline 24 and ablation 21 of 44, instead of 11, 25 and 22), and its correct part-number reads would be 9, not 10. Without `ESP-WROOM-02` the EasyOCR pipeline would have the right part in its top 3 for 34 photos instead of 33, and the rotation run's text channel would get 14 instead of 15. The photo marked ESP-WROOM-02 (ESP8266 56733450) would also count as a third legible marking the catalog does not cover, so of the 26 photos where the EasyOCR identifier found nothing, 22 rather than 23 would be OCR misses. No other count in this README changes.
- Sessions across parts. The split keeps every query out of its own reference photo's session, but sessions are grouped within a part only. Two queries (I8080 6691932 and MC68000 8041354) are by the photographer of the I8086 and I8088 reference photos, which can pull the image channel toward those parts. Without them the EasyOCR pipeline gets 26 of 42 (62%) and the image channel 17 of 42.
- Smaller renditions. 12 of the 209 files are stored at 330 or 500 px because Commons kept refusing the larger copies (HTTP 429). Two of them are queries (LM7805 177751130 at 330 px, ESP8266 56733450 at 500 px), and their labels were made on these smaller files.
- Local demo scope. The workbench adds local SQLite/FTS5 inference, optional VLM verification and measured playback. It has no production job service; image-vector search remains numpy. The original baseline's pg_trgm-like similarity remains implemented in Python.
