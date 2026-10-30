# Run `easyocr` (2026-10-30)

- Device: mps (Apple GPU); models loaded in 3.4 s
- Models: image `google/siglip-base-patch16-224` (revision `7fd15f0`), text `BAAI/bge-small-en-v1.5` (revision `5c38ec7`), OCR `easyocr`
- Catalog: 18 parts; 18 have a reference photo (18 photos), so the image channel can only rank those. No photo: none.
- Queries: 44 photos of 18 parts (43 with a legible part marking). Parts with a reference photo but no query: none.

## Accuracy (all queries)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 41% (18/44) | 28-56% | 41% (18/44) | 28-56% | 0.41 | 41% |
| text | 30% (13/44) | 18-44% | 52% (23/44) | 38-66% | 0.44 | 86% |
| image | 39% (17/44) | 26-53% | 61% (27/44) | 47-74% | 0.54 | 100% |
| fused | 61% (27/44) | 47-74% | 75% (33/44) | 61-85% | 0.71 | 100% |
| fused_no_text | 64% (28/44) | 49-76% | 80% (35/44) | 65-89% | 0.74 | 100% |
| chance, 18 parts | 6% | | 17% | | 0.16 | |

`fused` is the pipeline: identifier (strong hits only, when there are any), text and image channels combined with reciprocal rank fusion. `fused_no_text` is an ablation without the text channel. Queries cluster by part (up to 3 per part), so the Wilson intervals are, if anything, too narrow.

## Accuracy (queries with a legible part marking)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 42% (18/43) | 28-57% | 42% (18/43) | 28-57% | 0.42 | 42% |
| text | 30% (13/43) | 19-45% | 51% (22/43) | 37-65% | 0.44 | 86% |
| image | 40% (17/43) | 26-54% | 63% (27/43) | 48-76% | 0.55 | 100% |
| fused | 60% (26/43) | 46-74% | 74% (32/43) | 60-85% | 0.70 | 100% |
| fused_no_text | 65% (28/43) | 50-78% | 81% (35/43) | 67-90% | 0.75 | 100% |

## Paired top-1 comparisons

| Comparison | fused right, other wrong | other right, fused wrong | p (queries) | parts fused better | parts other better | p (parts) |
|---|---|---|---|---|---|---|
| fused vs identifier | 9 | 0 | 0.004 | 7 | 0 | 0.02 |
| fused vs text | 15 | 1 | <0.001 | 11 | 0 | <0.001 |
| fused vs image | 15 | 5 | 0.04 | 11 | 4 | 0.12 |
| fused vs fused_no_text | 4 | 5 | 1.00 | 3 | 4 | 1.00 |

Exact two-sided sign tests. The per-query test treats the queries of one part as independent, which they are not; the per-part test counts each part once and is the safer reading.

## Top-1 per part

| Part | Queries | identifier | text | image | fused | fused_no_text |
|---|---|---|---|---|---|---|
| NE555 | 3 | 2 | 0 | 2 | 2 | 2 |
| UA741 | 3 | 1 | 1 | 1 | 2 | 1 |
| ATMEGA328P | 3 | 1 | 1 | 1 | 2 | 1 |
| ATMEGA8 | 1 | 1 | 1 | 0 | 1 | 1 |
| LM7805 | 2 | 1 | 0 | 0 | 1 | 1 |
| LM317 | 3 | 1 | 0 | 0 | 1 | 1 |
| I8080 | 2 | 1 | 0 | 0 | 1 | 1 |
| I8085 | 1 | 0 | 0 | 0 | 0 | 0 |
| I8086 | 2 | 1 | 0 | 1 | 2 | 2 |
| I8088 | 3 | 2 | 1 | 0 | 2 | 2 |
| I80286 | 3 | 1 | 0 | 2 | 1 | 3 |
| Z80 | 3 | 2 | 2 | 0 | 2 | 2 |
| MC68000 | 3 | 1 | 1 | 1 | 3 | 1 |
| 2N3055 | 3 | 1 | 2 | 3 | 2 | 3 |
| MAX232 | 3 | 1 | 3 | 2 | 3 | 3 |
| ULN2003 | 1 | 0 | 0 | 0 | 0 | 0 |
| ESP8266 | 3 | 0 | 0 | 2 | 1 | 2 |
| ESP32 | 2 | 1 | 1 | 2 | 1 | 2 |
| mean over parts | | 41% | 29% | 34% | 58% | 61% |

## Look-alike families

| Family | Parts | Queries | image top-1 | image wrong, same family | fused top-1 | fused wrong, same family |
|---|---|---|---|---|---|---|
| 8-pin analog | NE555, UA741 | 6 | 3 | 1 | 4 | 0 |
| AVR ATmega | ATMEGA328P, ATMEGA8 | 4 | 1 | 0 | 3 | 0 |
| 3-pin regulators | LM7805, LM317 | 5 | 0 | 0 | 2 | 0 |
| Intel 8080-80286 | I8080, I8085, I8086, I8088, I80286 | 11 | 3 | 8 | 6 | 5 |
| Espressif Wi-Fi | ESP8266, ESP32 | 5 | 4 | 1 | 2 | 1 |

## Notes

- OCR read the correct part number: 39% of all queries, 40% of legible ones.
- Identifier channel fired on 18 queries; its top-1 was right 100% of the time.
- 2 legible queries carry a marking the catalog does not cover (I8088 `P80C88A-2`, UA741 `741P`): a perfect read would match none of the part's aliases exactly or glyph-folded (an alias shorter than 4 characters, such as `741`, never counts inside a longer word), or another part would match it better. On the other 41 legible queries OCR read the part number 41% of the time.
- 0 queries share the author of their own part's reference photo (a different session). Without them: image top-1 39% (17/44), fused top-1 61% (27/44).
- 2 queries are by the photographer of another part's reference photo, which can pull the image channel toward that part: 6691932.jpg (I8080; photographer of the I8086/I8088 reference), 8041354.jpg (MC68000; photographer of the I8086/I8088 reference). Without them: image top-1 40% (17/42), fused top-1 62% (26/42).

## Latency per query (ms, warm: second pass over the same photos)

| Stage | n | p50 | p95 | mean | first-pass mean |
|---|---|---|---|---|---|
| ocr | 44 | 108 | 212 | 110 | 163 |
| identifier | 44 | 1 | 3 | 1 | 1 |
| text | 38 | 5 | 5 | 5 | 5 |
| image | 44 | 16 | 18 | 16 | 16 |
| fusion | 44 | 0 | 0 | 0 | 0 |
| total | 44 | 128 | 239 | 131 | 185 |

The text stage only counts queries where the channel ran; it abstains when OCR finds no token of 3 or more letters or digits.

## Fused top-1 misses (17)

| Query | Truth | Fused top-3 | OCR text |
|---|---|---|---|
| 80876576.jpg | 2N3055 | I8080, I80286, I8088 | 76055,p |
| 75189907.jpg | ATMEGA328P | LM317, ULN2003, ATMEGA8 | (none) |
| 97701682.jpg | ESP32 | ESP8266, I80286, ESP32 | 4 0 0 8 9 3 4ad 262020 Uboops7w8i 8 |
| 54458803.jpg | ESP8266 | MAX232, I80286, ULN2003 | 0 2 4 '0 77 TCC "CPO 341015- 14p1012, 3 RXD '6P10S , 6P104 ' |
| 56733450.jpg | ESP8266 | I80286, I8080, ATMEGA328P | 1 8 (e1177 10 20 30 No0 /A 7B |
| 5174316.jpg | I80286 | I8085, I80286, Z80 | N88286542 50258592 lee '82 485 |
| 6976587.jpg | I80286 | I8085, I8080, I80286 | 1s5288670 @(i '8 2 8 5 |
| 6691932.jpg | I8080 | I8088, I80286, ATMEGA328P | "74 79 28888657 |
| 55534910.jpg | I8085 | I80286, I8086, I8088 | c2oe5a 45778' INtel 76' |
| 78876305.jpg | I8088 | I8085, I8088, I80286 | PBOC88A 2 0 INTEL78 027030J2 JAPAN |
| 23636678.jpg | LM317 | ULN2003, LM317, I80286 | 3 8 |
| 74886172.jpg | LM317 | ULN2003, LM317, LM7805 | La3}7T GHODU WJ 040 M U |
| 194982655.jpg | LM7805 | ULN2003, LM317, I80286 | 0 4 mc 4g |
| 20729665.jpg | NE555 | LM7805, ATMEGA328P, MAX232 | 8809VL |
| 64573796.jpg | UA741 | MAX232, ATMEGA328P, ULN2003 | 2741P 84145 |
| 126915852.jpg | ULN2003 | MAX232, ATMEGA328P, LM7805 | (none) |
| 55550822.jpg | Z80 | I8086, ATMEGA328P, ATMEGA8 | l |
