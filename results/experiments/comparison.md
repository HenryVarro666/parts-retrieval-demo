# OCR and Top-10 VLM development experiments

44 query photos / 18 catalog classes; unchanged model-generated labels. This is development evaluation, not a new blind test.

| Run | Top-1 | Top-3 | Recall@10 | Wins / regressions vs baseline | p50 / p95 ms |
|---|---|---|---|---|---|
| easyocr_views | 29/44 | 33/44 | 42/44 | 6 / 4 | 1028 / 1928 |
| easyocr_whole | 27/44 | 33/44 | 43/44 | 0 / 0 | 180 / 365 |
| qwen_vlm_top10 | 39/44 | 41/44 | 43/44 | 13 / 1 | 5798 / 7431 |
| rapidocr_views | 38/44 | 40/44 | 42/44 | 13 / 2 | 750 / 1238 |
| rapidocr_whole | 35/44 | 40/44 | 42/44 | 10 / 2 | 129 / 210 |

OCR runs use one untimed query warmup and one measured pass. VLM timing sums cached baseline stage time and separately measured generation; it excludes model load and is not measured end-to-end. CPU ONNX OCR and MPS PyTorch OCR are different runtime paths.

Whole versus views compares eight predefined views and catalog-guided view selection together. It does not isolate cropping from rotation or hypothesis selection. Neither labels nor catalog aliases were patched after inspecting errors. VLM sees only query pixels, shuffled candidate metadata and reference photos, never ground truth or review notes.
