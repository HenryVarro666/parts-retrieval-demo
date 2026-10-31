# Project guidance

## Start here

- Read [documentation index](docs/README.md), [current handoff](docs/HANDOFF.md), and [issue/improvement ledger](docs/ISSUES_AND_IMPROVEMENTS.md) before changing the pipeline.
- This repository identifies catalog components from photos. The separate photovoltaic reconstruction repository is `/Users/caochao/Documents/2Dto3D`; its current code, data policy and work belong there. The earlier `/Users/caochao/Documents/ChatGPT/2Dto3D` directory is a research/learning workspace.
- Parent instructions still apply. The code graph has previously been empty; attempt graph context before falling back to source search.

## Required documentation on every task

The user requires previous, current and future problems and improvements to be saved and connected. Documentation is part of delivery, including failed attempts.

1. Before work, identify the relevant `PR-xxx` issue or add one to `docs/ISSUES_AND_IMPROVEMENTS.md`. Record the observed trigger, affected sample/run, evidence and current status. Separate observations from suspected causes.
2. For a substantive change/experiment, save a dated record under `docs/research/`. Include input manifest/hash, code/model/config versions, hardware, commands, baseline, actual change, before/after results, latency scope, regressions, failure cases and remaining limitations. Proposed or unexecuted work must remain labeled accordingly.
3. Update the issue's resolution/evidence and `docs/HANDOFF.md` with the latest verified state and concrete next action. Add new documents to `docs/README.md`; do not leave evidence reachable only from chat.
4. Preserve frozen inputs, raw OCR, model judgments and historical reports. Use a new run/output path for a new comparison. A correction needs a dated addendum or new version; never rewrite history to hide a failure or make an old proposal look completed.
5. Keep status precise: proposed, implemented, tested, model-evaluated, browser-checked and remotely synchronized are different claims. Unit tests alone do not establish recognition accuracy, geometry quality or measurement precision. Same-machine clone verification does not establish CUDA/different-hardware performance.
6. At handoff, verify links/paths and metric denominators against saved artifacts. Record what was actually checked this turn and what is inherited evidence. Commits/pushes follow the current conversation's authorization; logging future work does not authorize new publication or model services.

## Experiment boundaries

- Ground truth, filenames, source descriptions and review transcriptions are for scoring/display, never inference prompts or query-derived catalog aliases.
- Distinguish the historical 44 queries, duplicate controls, same-object hypotheses and all-view single-image measurements. Keep still photographs and video viewpoints identifiable; do not count 3N photos as 3N physical objects.
- Preserve policy/model/catalog choices within a frozen comparison. Correct-candidate recall and downstream reranking accuracy are separate. A strong alias or model explanation can be wrong.
- Record actual end-to-end timing scope, initialization, cold/warm conditions and cache hits; do not relabel stage sums or replay as fresh measured inference.
- Public licensed evaluated sources are tracked with attribution. Private uploads, model weights, environments and runtime caches remain ignored. Never copy the other project's raw photographs/assets into this repository merely to complete documentation.

## Verification commands

```bash
uv run --frozen --extra experiments pytest -q
node --test tests/web_i18n.test.cjs tests/web_multi_image.test.cjs tests/web_app_multi.test.cjs
uv run --frozen python -I -m partsid.multi_image_experiments report
git diff --check
```

Choose checks appropriate to the change. Documentation-only work needs factual/link checks; do not rerun heavy models without a reason. Rebuilding the paired report validates and rewrites generated summaries, so preserve/check its diff.
