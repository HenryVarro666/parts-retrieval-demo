# Integration notes: retained OCR evidence and local VLM

Checked 2026-10-30. Interface research only; example parameters are not accuracy claims.

## Existing adapter points

`Pipeline.run(path)` only requires `ocr.read(path) -> str`, then independently computes identifier, text and image rankings. Its return includes OCR text, identifier hits, all rankings, image similarities and stage timing. Wrap its OCR argument with a new evidence adapter, retain the original pipeline and baseline files, and write experiments to separate outputs. Reuse `build_index` once per process, not per query. Existing result CSV truncates OCR to 120 characters and cannot recover bbox/confidence. [Pipeline](../../partsid/evaluate.py#L79), [index](../../partsid/evaluate.py#L72), [old OCR](../../partsid/ocr.py#L18).

Minimal richer evidence result: `text`, `selected_view`, `views`, `conflicts`. Each view records its crop in original pixels, right-angle rotation, resulting width/height, OCR text, list of `{points, text, confidence}` boxes in view coordinates, and measured milliseconds. Never join text from different alternative views into one string: adjacency joins could create nonexistent part numbers. Select a single view by a predeclared catalog-only policy and record that catalog guidance in metadata. Preserve original view even when crops are available. Query label, review and filename must never enter view scoring or VLM prompts.

## RapidOCR 3.10.0 verified interfaces

Use package `rapidocr==3.10.0` plus a separately installed CPU backend such as `onnxruntime==1.31.1`. RapidOCR itself does not depend on ONNX Runtime. Its 3.10.0 defaults are detector PP-OCRv6 small, classifier PP-OCRv4 mobile, recognizer PP-OCRv6 small; do not describe an unconfigured RapidOCR run as PP-OCRv5. Constructor loads models lazily on first use, so initialization time alone is not model-load timing. [Versioned config](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/config.yaml), [usage](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/), [PyPI metadata](https://pypi.org/pypi/rapidocr/3.10.0/json).

`engine(np_rgb_or_bgr_image)` returns `RapidOCROutput` in the default detection+recognition path: `boxes` numpy array, `txts` tuple, `scores` tuple, and `elapse_list`/`elapse` in seconds. All box/text/score fields may be None for an empty result. Use explicit `is None`/`len`, never numpy truth testing. `result.to_json()` is also available but returns None for missing fields. Call supports `use_det`, `use_cls`, `use_rec`, `text_score`, `box_thresh`, `unclip_ratio`. [Output dataclass](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/utils/output.py#L16), [call signature](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/main.py#L93).

Explicit routes:

- PP-OCRv5 detector accepts `Det.lang_type='ch'` or `'multi'`, model size `mobile`/`server`.
- PP-OCRv5 English recognition is `Rec.lang_type='en'`, `Rec.model_type='mobile'`, `Rec.ocr_version=OCRVersion.PPOCRV5`; Latin is `'latin'`, also `mobile`. English+server is not a route; only Chinese server recognition is listed.
- PP-OCRv6 recognition with `'en'` selects the shared multilingual PP-OCRv6 weights; it is not a separate English specialist. Available sizes: `tiny`, `small`, `medium`.
- To force CPU: `Det/Cls/Rec.engine_type=EngineType.ONNXRUNTIME`, and `EngineConfig.onnxruntime.use_cuda=False`, `use_coreml=False`, `use_dml=False`, `use_cann=False`. Record actual provider list and actual downloaded ONNX names/hashes, not merely desired config. [Route matrix](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml#L149), [en and Latin entries](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml#L174), [enum spellings](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/utils/typings.py#L47).

Model routing includes official SHA256 values; pin package version and retain actual model hashes. ONNX confidence scores are model outputs, not calibrated probability of the identified part. Any strong alias conflict across views must remain visible even if one view is selected.

## MLX VLM exact API

`mlx-vlm==0.7.11` requires `transformers>=5.14.0`; isolate it from the original baseline environment. Suggested model `mlx-community/Qwen3-VL-4B-Instruct-4bit`, exact revision `2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b`. Its config declares built-in `qwen3_vl`, no `model_file`/`auto_map`, and repository lists no Python model code. `load(..., revision=REVISION, trust_remote_code=False)` routes through MLX-VLM built-in architecture. A pinned local snapshot avoids accidental model config drift. [Model API](https://huggingface.co/api/models/mlx-community/Qwen3-VL-4B-Instruct-4bit), [model files](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit/tree/2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b), [built-in implementation](https://github.com/Blaizzy/mlx-vlm/tree/v0.7.11/mlx_vlm/models/qwen3_vl), [load](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/utils.py#L823), [package requirements](https://pypi.org/pypi/mlx-vlm/0.7.11/json).

```python
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config
model, processor = load(model_id, revision=revision, trust_remote_code=False)
config = load_config(model_id, revision=revision)
prompt = apply_chat_template(processor, config, instruction, num_images=len(images))
output = generate(model, processor, prompt, image=images, max_tokens=256,
                  temperature=0.0, verbose=False, max_pixels=1048576, min_pixels=65536)
raw_text = output.text
```

`generate` returns `GenerationResult`, not a string: `.text`, token counts, prompt/generation TPS, `.peak_memory`, `.finish_reason`. Preserve raw response and parse JSON defensively. [Result schema](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/generate/common.py#L278), [generate](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/generate/dispatch.py#L1198).

`resize_shape` is ignored with a BaseImageProcessor; use `max_pixels`/`min_pixels` instead. Qwen3 processor forwards these to its image resizer. This checkpoint declares pixel budgets min 65536, max 16777216, so a large contact sheet can use excessive tokens/memory. The example 1048576 maximum is a fixed resource cap to test, not an established optimum. Prefer separate query/crop and candidate-reference images over shrinking all tiny text into a contact sheet. Record cap and resulting view dimensions. [Ignored resize](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/utils.py#L1322), [size forwarding](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.11/mlx_vlm/utils.py#L1815), [checkpoint size](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit/blob/2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b/preprocessor_config.json#L34).

## Frozen candidate and failure contract

First create candidate lists from baseline rankings using fixed retrieval-only rules. Preserve all baseline Top10 exactly; do not append truth, review aliases or expected marking. Deterministically shuffle presentation independent of gt. VLM may only select an ID in the supplied set or abstain. Reject malformed output, duplicate/unknown ID, empty text and explicit uncertainty; retain baseline order and raw response on abstention. Report candidate recall@10 alongside reranked Top1 so errors that could not be recovered by reranking remain visible. A pure OCR prompt can omit all candidates; later candidate reranking is a separate condition.

Checkpoint each image before moving on; distinguish completed, partial and failed runs. Measure wall-clock inference separately from cached playback and initialization. Handle no text as a valid empty evidence result; dependency/model/provider failure is an explicit error, never a silent baseline fallback presented as a new-model run. Serial inference or a lock is necessary because readers/processors and their last-result state are mutable. For web uploads validate the decoded image and bounded dimensions, use generic filenames, serve only allowlisted dataset images, and keep server loopback-only by default.


## Implemented adapter handoff

`partsid/evidence_ocr.py` now exposes the approved `EvidenceOCR` constructor and retained evidence. An important decoder ruling: installed EasyOCR 1.7.2 uses RGB skimage input for its file-path detector and a separately cv2-decoded grayscale image for recognition, but treats 3-channel numpy arrays as BGR. Original whole/0-degree views therefore keep `readtext(str(path), detail=1)` to preserve the baseline decoder; all transformed views use contiguous BGR arrays without temporary image files. This distinction is explicit in metadata and belongs to the multiview preprocessing ablation. RapidOCR arrays are also BGR. Input files must be upright; the original evaluator already normalizes EXIF.

Actual smoke on stored LM317/75704312.jpg: EasyOCR whole output exactly equals the original CSV string and retains 13 boxes. RapidOCR whole retains 10 boxes and reads `ON LM 317T`; its actual provider is `CPUExecutionProvider`. Collected model identities:

- EasyOCR detector `craft_mlt_25k.pth`, SHA256 `4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17`.
- EasyOCR recognizer `english_g2.pth`, SHA256 `e2272681d9d67a04e2dff396b6e95077bc19001f8f6d3593c307b9852e1c29e8`.
- Rapid detector `PP-OCRv6_det_small.onnx`, SHA256 `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`.
- Rapid classifier `ch_ppocr_mobile_v2.0_cls_mobile.onnx`, SHA256 `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`.
- Rapid recognizer `PP-OCRv6_rec_small.onnx`, SHA256 `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.

TDD evidence: new 10 behavioral tests first failed because `partsid.evidence_ocr` did not exist; after implementation they passed. They cover fixed geometry, BGR convention, original-path decoding, confidence/box retention, empty output, single-view choice, conflicting strong identifiers, no cross-view invented joins, and explicit errors clearing old evidence. Full-suite invocation during concurrent implementation was temporarily blocked by `tests/test_web.py` importing the still-unimplemented `partsid.web`; this was reported to the root implementer, who owns final whole-branch verification. No original baseline source/result/label/catalog file was edited by this worker.
