# Public same-object triplet expansion

User-authorized continuation: collect public photographs, compare fixed single/three-image pipelines, update the local trilingual demo and private GitHub repository.

## Frozen design

- Add seven physical-unit hypotheses: UA741, ULN2003, ATMEGA328P, I8088, Z80, MC68000, ESP8266. Retain the previous I80286 anchor, for eight groups / 24 views.
- All groups remain exploratory and visually supported; none has explicit owner confirmation. I8088 uses three actual camera viewpoints from one video and is reported separately. Blur/occlusion stress views remain included and marked.
- Root visually reviewed all selected target ROIs and catalog references before inference. Preserve source, license, independent-capture evidence, integer crop coordinates and hashes in a frozen selection file. Use chronological capture order for new groups; keep the historical anchor order.
- Exclude derivatives of one capture, different units, invisible targets and wrong chip variants. Source metadata and labels never enter inference.
- Freeze catalog, aliases, OCR/model versions, prompts, fusion and acceptance thresholds. No selection or tuning based on outcomes. Preserve historical results.

## Implementation and verification

1. Store licensed source copies and deterministic PNG crops; add an offline preparation script and source/rejection audit. Validate capture IDs in addition to pixels, including catalog overlap.
2. Extend the evaluator with optional standalone runs for every view. Headline paired baseline is the first predetermined image versus all three; supplementary single-image accuracy uses 24 views clustered in eight groups. Measure fresh extraction in both paths, shared loaded retrieval models, requested VLM process/load included, with no historical VLM cache.
3. Run retrieval-only, normal selective VLM and forced VLM policies sequentially. Save per-object outcomes, Top-1/Top-3/Recall@10, gains/regressions, median/p95 latency and separate still/video and quality strata.
4. Show expanded cohort, per-group replay, source credit, quality notes and individual-view results in Chinese/English/Spanish. Keep OCR and model identifiers unchanged. Warm translations for newly saved model prose.
5. Add meaningful regression tests, run existing Python/Node suites, inspect the real browser in three languages, and obtain an independent review. Push to the existing private repository, then verify a fresh GitHub clone and record reproducibility evidence.

## Interpretation boundary

Eight selected units are an exploratory stress set, not a representative accuracy estimate. Two added groups reuse one capture each from the historical 44 queries; the anchor is also reused. A chronological first-view baseline may be unusually easy or hard, so publish all-view single results alongside it. Do not claim that adding images always improves recognition.
