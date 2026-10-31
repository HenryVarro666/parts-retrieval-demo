# OCR/VLM ensemble review · 2026-10-30

**PASS. No unresolved material findings in the reviewed delta.**

Reviewed `partsid/ensemble.py`, its focused tests, the new result artifacts, and the latest `partsid/web.py`, `web/app.js`, `web/index.html`, and README changes against the fixed-policy spec.

- Decisions use predictions only. Strong acceptance requires one >=0.9 identifier agreeing with RapidOCR Top-1 and no cross-view conflict. Invalid or abstaining VLM selections contribute no vote. RRF uses the VLM selection alone, without its inherited OCR tail.
- All five outputs contain the same 44 aligned queries. Recomputed every decision, cost, summary, and paired count; checked source/label SHA256 values and unchanged source files against `f0252ce`. Strong gating reproduces 40/44, two gains and zero regressions versus RapidOCR views, with eight simulated VLM calls.
- Costs include complete required OCR branches once and generation even on abstention. Metadata, report, README, and UI identify offline replay and estimated serial costs, excluding model load and measured end-to-end service claims.
- UI payloads preserve readable policy labels and RapidOCR evidence attribution, expose VLM evidence only for consulted branches, and retain OCR-only live uploads.

🟡 **Resolved metadata mismatch:** `partsid/ensemble.py:153` now records RRF's actual tie rule, best single-channel rank then ID. The former shared voting-rule description was inaccurate. Existing RRF behavior coverage checks the differing tied order; output metadata was verified after regeneration.

Validation: `uv run --extra experiments pytest tests/test_ensemble.py tests/test_web.py -q` passed **11 tests**; `node --check web/app.js` passed. Additional CPU-only checks covered all-policy label independence, invalid/abstaining VLM exclusion, gate ambiguity/threshold/conflict boundaries, cost accounting, full artifact consistency, and web payload call flags.

Limits: static code and saved-output replay review; no new inference, training, live upload execution, browser rendering, remote visibility, or fresh-clone verification in this review. Browser QA and remote verification belong to the parent task. These 44 development queries do not establish independent generalization or real selective-service latency.
