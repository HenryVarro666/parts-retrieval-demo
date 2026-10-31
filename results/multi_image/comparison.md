# Single / multi-photo paired comparison

Historical 44-photo experiments remain unchanged. Duplicate controls do not measure multi-angle benefit. Visually supported same-object groups are exploratory, not owner/expert-confirmed. Single runs first with loaded retrieval models shared; fresh query extraction in both paths, requested VLM process/loading included.

| Run / scope | Groups / control sources | Top-1 single / multi | Top-3 | Recall@10 | p50 ms single / multi | gains / regressions |
|---|---:|---:|---:|---:|---:|---:|
| duplicate_control.json / duplicate_control | 44 | 38/44 / 38/44 | 40 / 40 | 42 / 42 | 816.9 / 809.9 | +0 / -0 |
| paired_retrieval.json / exploratory_same_object | 1 | 1/1 / 1/1 | 1 / 1 | 1 / 1 | 1042.4 / 1965.8 | +0 / -0 |
| paired_visual.json / exploratory_same_object | 1 | 1/1 / 1/1 | 1 / 1 | 1 / 1 | 8671.1 / 8577.9 | +0 / -0 |
