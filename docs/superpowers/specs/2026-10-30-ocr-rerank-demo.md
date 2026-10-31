# OCR experiments and evidence demo

The user approved reviewing the 17 baseline errors, testing a new OCR and Top-10 visual reranking, and building a lightweight page showing evidence, candidates, and before/after results. They also requested a current GitHub OCR survey.

## Scope

- Preserve the catalog, labels, and existing baseline reports. Add a separate model visual review of all 17 errors, with uncertainty; it is neither blind nor expert gold.
- Compare EasyOCR and RapidOCR 3.10.0 / ONNX Runtime CPU on all 44 queries. Cross whole-image and deterministic central crop / right-angle views; record catalog-guided view selection separately from the OCR model. Keep text boxes, text, scores, view geometry, timing, model identity and hashes.
- Run an actual local visual-language model on the frozen baseline Top-10 candidates for every query, with no ground truth, filename, review or label text in the prompt. Shuffle candidate presentation deterministically. Use query pixels and reference thumbnails plus public catalog fields. Allow abstention; reject invalid IDs; preserve the original order on abstention or invalid output. Report wins and regressions, not just the original errors.
- Use a pinned small MLX Qwen3-VL quantized model in an isolated environment so the original torch / transformers environment stays unchanged. No training or paid inference.
- Build a local single-page Python/HTML demo: preset queries and image upload, inspect OCR evidence, compare measured runs, show Top-3 reference images, review notes, latency and true evaluation scope. Cached experiment playback and live upload inference must be clearly distinct.
- Keep the page responsive and keyboard usable. Escape model/catalog text, constrain image serving to dataset photos, validate uploads, serialize model inference, bind to loopback by default.
- GitHub survey records exact stars and timestamp, official implementation sources, maintenance and licenses. Stars do not imply component-photo accuracy.

## Display

A restrained industrial lab style: warm off-white canvas, dark ink, teal evidence overlays, orange uncertainty. One workbench with a sample picker, large source image, evidence panel, three candidates, and a compact experiment comparison. Metrics display the 44-photo, 18-class development evaluation and label limitations.

## Acceptance

All 17 reviews are traceable; actual measured experiment JSON and a paired summary exist; baseline files remain byte-identical; the web page runs locally, displays actual results, and successfully handles a live image inference. Tests cover candidate constraints, abstention, prompt leakage, view selection conflicts, and HTTP file/upload boundaries. Complete browser QA and a fresh review before claiming completion.
