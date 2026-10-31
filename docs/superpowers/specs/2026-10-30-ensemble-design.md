# OCR and VLM combination experiment

The user explicitly authorized pushing code, results and the page to the existing private GitHub repository, and requested testing vote-like OCR/VLM combinations. This extends the approved local experiment and web workflow. No new model, training or paid API is needed for the first comparison.

## Fixed policies, defined before evaluation

All policies use the frozen outputs from the same 44 queries. Decision functions receive predictions and public catalog identifiers, never ground truth, file-based labels or model-review transcriptions. A validated VLM abstention supplies no vote. Model self-reported confidence is not a probability.

1. `ensemble_vote5`: each of four OCR pipelines (EasyOCR whole/views, RapidOCR whole/views) and the valid VLM selection receives one vote. This intentionally naive baseline double-counts correlated OCR variants. Equal vote totals use RapidOCR views order, then ID.
2. `ensemble_family_vote`: one vote per representative family: EasyOCR whole, RapidOCR views, validated VLM selection. Same deterministic tie rule.
3. `ensemble_rrf`: equal reciprocal-rank fusion (existing k=60, top-10) of EasyOCR whole and RapidOCR views rankings plus the valid VLM selection as a singleton ranking. The singleton avoids counting the VLM's inherited baseline tail as an independent visual opinion. Existing RRF tie handling stays unchanged.
4. `ensemble_strong_gate`: accept RapidOCR views only when exactly one identifier has score >=0.9 (an exact/glyph-folded alias score, not OCR probability), its part equals fused Top-1, and no cross-view strong-ID conflict exists. Otherwise consult the validated VLM and use its selection, or retain RapidOCR views on VLM abstention.
5. `ensemble_disagreement_gate`: run EasyOCR whole and RapidOCR views; accept their shared Top-1, otherwise consult the VLM with the same fallback.

Vote rankings sort by vote count then the fixed tie rule; zero-vote candidates retain RapidOCR views order. A gating decision promotes its chosen ID and retains RapidOCR views order for the rest; a VLM selection may enter from its original baseline Top-10. All policies retain traceable votes, branch decisions and VLM-call flags. No per-example rule exceptions or fitted weights.

## Measurements and limitations

Report all 44 queries, Top-1/Top-3/Recall@10, paired wins/regressions versus both original baseline and RapidOCR views, invocation counts, selected-source evidence and source-file SHA256 values. Compute actual model complementarity as diagnosis only; never count a ground-truth oracle as an implemented policy.

This first combination experiment is an offline replay of actual saved model outputs. Inference is not re-run, because inputs, candidates, prompts and weights stay frozen. Estimated serial cost sums complete OCR branches required by the policy, including EasyOCR candidate generation whenever a gated VLM call needs it; that candidate branch is counted once. No unimplemented cross-branch shared-encoder optimization or parallel scheduling is assumed. These are stage-sum estimates excluding model load, not measured end-to-end latency or newly measured selective deployment savings. A VLM that abstains still incurs generation cost when called.

Retain original result artifacts unchanged. New combination runs appear as measured-output replay on the existing page with vote/routing details and timing labels. Live upload continues to be OCR only. Provide a one-command CPU replay on other machines, document model weights as downloads rather than committing caches, and verify a clean remote clone. Push only to the confirmed existing private repository, preserving history with fast-forward updates.
