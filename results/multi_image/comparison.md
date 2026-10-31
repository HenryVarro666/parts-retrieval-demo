# Single / multi-photo paired comparison

Historical 44-photo experiments remain unchanged. Duplicate controls do not measure multi-angle benefit. Visually supported same-object groups are exploratory, not owner/expert-confirmed. Single runs first with loaded retrieval models shared; fresh query extraction in both paths, requested VLM process/loading included.

| Run / scope | Groups / control sources | Top-1 single / multi | Top-3 | Recall@10 | p50 ms single / multi | gains / regressions |
|---|---:|---:|---:|---:|---:|---:|
| duplicate_control.json / duplicate_control | 44 | 38/44 / 38/44 | 40 / 40 | 42 / 42 | 816.9 / 809.9 | +0 / -0 |
| paired_retrieval.json / exploratory_same_object | 1 | 1/1 / 1/1 | 1 / 1 | 1 / 1 | 1042.4 / 1965.8 | +0 / -0 |
| paired_visual.json / exploratory_same_object | 1 | 1/1 / 1/1 | 1 / 1 | 1 / 1 | 8671.1 / 8577.9 | +0 / -0 |
| public_gated.json / exploratory_same_object | 8 | 7/8 / 8/8 | 8 / 8 | 8 / 8 | 1119.8 / 6004.1 | +1 / -0 |
| public_retrieval.json / exploratory_same_object | 8 | 6/8 / 6/8 | 8 / 7 | 8 / 8 | 867.5 / 2519.8 | +0 / -0 |
| public_visual.json / exploratory_same_object | 8 | 8/8 / 8/8 | 8 / 8 | 8 / 8 | 7137.7 / 10371.9 | +0 / -0 |

## public_gated.json: frozen public triplets

First predetermined view vs all three; auxiliary all-single results measure every view independently, not 3N independent objects. Still/video, new/anchor and unreadable-marking quality strata (including glare) are separate in report.json.

All single views: 20/24 Top-1, 8 object clusters; p50/p95 1210.9/7495.4 ms.
Paired p95 single/multi: 7062.1/10197.9 ms.

| Object / label / capture | Standalone views 1 / 2 / 3 | Three-view Top-1 | Paired time ms single / multi |
|---|---|---|---:|
| public-01 / UA741 / still_photo | UA741 / UA741 / UA741 | UA741 | 1070.2 / 2403.5 |
| public-02 / ULN2003 / still_photo | ULN2003 / ULN2003 / ULN2003 | ULN2003 | 7539.9 / 9699.8 |
| public-03 / ATMEGA328P / still_photo | ATMEGA8 / ATMEGA328P / Z80 | ATMEGA328P | 1046.5 / 10466.2 |
| public-04 / I8088 / video_frame | I8088 / I8088 / I8088 | I8088 | 800.7 / 2797.1 |
| public-05 / Z80 / still_photo | Z80 / ATMEGA8 / Z80 | Z80 | 1230.3 / 3927.5 |
| public-06 / MC68000 / still_photo | MC68000 / MC68000 / MC68000 | MC68000 | 1169.5 / 3431.0 |
| public-07 / ESP8266 / still_photo | ESP8266 / ESP8266 / Z80 | ESP8266 | 6174.8 / 8080.7 |
| anchor-01 / I80286 / still_photo | I80286 / I80286 / I80286 | I80286 | 788.4 / 8670.0 |

## public_retrieval.json: frozen public triplets

First predetermined view vs all three; auxiliary all-single results measure every view independently, not 3N independent objects. Still/video, new/anchor and unreadable-marking quality strata (including glare) are separate in report.json.

All single views: 17/24 Top-1, 8 object clusters; p50/p95 938.2/1290.4 ms.
Paired p95 single/multi: 1132.9/3590.5 ms.

| Object / label / capture | Standalone views 1 / 2 / 3 | Three-view Top-1 | Paired time ms single / multi |
|---|---|---|---:|
| public-01 / UA741 / still_photo | UA741 / UA741 / UA741 | UA741 | 1143.7 / 2428.2 |
| public-02 / ULN2003 / still_photo | ULN2003 / ULN2003 / ULN2003 | ULN2003 | 784.1 / 2487.5 |
| public-03 / ATMEGA328P / still_photo | ATMEGA8 / ULN2003 / Z80 | ATMEGA8 | 950.9 / 3326.3 |
| public-04 / I8088 / video_frame | I8088 / I8088 / I8088 | I8088 | 705.8 / 2552.0 |
| public-05 / Z80 / still_photo | Z80 / ATMEGA8 / Z80 | Z80 | 1112.9 / 3732.8 |
| public-06 / MC68000 / still_photo | MC68000 / MC68000 / MC68000 | MC68000 | 1061.8 / 3084.4 |
| public-07 / ESP8266 / still_photo | ESP32 / I80286 / Z80 | I80286 | 648.8 / 1660.2 |
| anchor-01 / I80286 / still_photo | I80286 / I80286 / I80286 | I80286 | 677.6 / 2018.6 |

## public_visual.json: frozen public triplets

First predetermined view vs all three; auxiliary all-single results measure every view independently, not 3N independent objects. Still/video, new/anchor and unreadable-marking quality strata (including glare) are separate in report.json.

All single views: 21/24 Top-1, 8 object clusters; p50/p95 7214.6/9089.4 ms.
Paired p95 single/multi: 7715.4/11598.0 ms.

| Object / label / capture | Standalone views 1 / 2 / 3 | Three-view Top-1 | Paired time ms single / multi |
|---|---|---|---:|
| public-01 / UA741 / still_photo | UA741 / UA741 / UA741 | UA741 | 7283.1 / 10875.0 |
| public-02 / ULN2003 / still_photo | ULN2003 / ULN2003 / ULN2003 | ULN2003 | 6786.3 / 10068.7 |
| public-03 / ATMEGA328P / still_photo | ATMEGA328P / ATMEGA328P / Z80 | ATMEGA328P | 7776.6 / 11742.1 |
| public-04 / I8088 / video_frame | I8088 / I8088 / I8088 | I8088 | 7174.1 / 9922.5 |
| public-05 / Z80 / still_photo | Z80 / ATMEGA8 / Z80 | Z80 | 7101.3 / 11330.3 |
| public-06 / MC68000 / still_photo | MC68000 / MC68000 / MC68000 | MC68000 | 7601.7 / 10675.1 |
| public-07 / ESP8266 / still_photo | ESP8266 / ESP8266 / Z80 | ESP8266 | 6226.0 / 8499.5 |
| anchor-01 / I80286 / still_photo | I80286 / I80286 / I80286 | I80286 | 6328.9 / 8735.7 |
