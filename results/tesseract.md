# Run `tesseract` (2026-10-30)

- Device: mps (Apple GPU); models loaded in 1.1 s
- Models: image `google/siglip-base-patch16-224` (revision `7fd15f0`), text `BAAI/bge-small-en-v1.5` (revision `5c38ec7`), OCR `tesseract`
- Catalog: 18 parts; 18 have a reference photo (18 photos), so the image channel can only rank those. No photo: none.
- Queries: 44 photos of 18 parts (43 with a legible part marking). Parts with a reference photo but no query: none.

## Accuracy (all queries)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 5% (2/44) | 1-15% | 5% (2/44) | 1-15% | 0.05 | 5% |
| text | 5% (2/44) | 1-15% | 11% (5/44) | 5-24% | 0.08 | 23% |
| image | 39% (17/44) | 26-53% | 61% (27/44) | 47-74% | 0.54 | 100% |
| fused | 43% (19/44) | 30-58% | 64% (28/44) | 49-76% | 0.58 | 100% |
| fused_no_text | 39% (17/44) | 26-53% | 66% (29/44) | 51-78% | 0.57 | 100% |
| chance, 18 parts | 6% | | 17% | | 0.16 | |

`fused` is the pipeline: identifier (strong hits only, when there are any), text and image channels combined with reciprocal rank fusion. `fused_no_text` is an ablation without the text channel. Queries cluster by part (up to 3 per part), so the Wilson intervals are, if anything, too narrow.

## Accuracy (queries with a legible part marking)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 5% (2/43) | 1-15% | 5% (2/43) | 1-15% | 0.05 | 5% |
| text | 5% (2/43) | 1-15% | 12% (5/43) | 5-24% | 0.09 | 23% |
| image | 40% (17/43) | 26-54% | 63% (27/43) | 48-76% | 0.55 | 100% |
| fused | 44% (19/43) | 30-59% | 65% (28/43) | 50-78% | 0.59 | 100% |
| fused_no_text | 40% (17/43) | 26-54% | 67% (29/43) | 53-80% | 0.58 | 100% |

## Paired top-1 comparisons

| Comparison | fused right, other wrong | other right, fused wrong | p (queries) | parts fused better | parts other better | p (parts) |
|---|---|---|---|---|---|---|
| fused vs identifier | 17 | 0 | <0.001 | 11 | 0 | <0.001 |
| fused vs text | 17 | 0 | <0.001 | 11 | 0 | <0.001 |
| fused vs image | 3 | 1 | 0.62 | 3 | 1 | 0.62 |
| fused vs fused_no_text | 3 | 1 | 0.62 | 3 | 1 | 0.62 |

Exact two-sided sign tests. The per-query test treats the queries of one part as independent, which they are not; the per-part test counts each part once and is the safer reading.

## Top-1 per part

| Part | Queries | identifier | text | image | fused | fused_no_text |
|---|---|---|---|---|---|---|
| NE555 | 3 | 0 | 0 | 2 | 2 | 2 |
| UA741 | 3 | 1 | 1 | 1 | 2 | 1 |
| ATMEGA328P | 3 | 0 | 0 | 1 | 1 | 1 |
| ATMEGA8 | 1 | 0 | 0 | 0 | 0 | 0 |
| LM7805 | 2 | 0 | 0 | 0 | 0 | 0 |
| LM317 | 3 | 0 | 0 | 0 | 0 | 0 |
| I8080 | 2 | 0 | 0 | 0 | 0 | 0 |
| I8085 | 1 | 0 | 0 | 0 | 0 | 0 |
| I8086 | 2 | 0 | 0 | 1 | 1 | 1 |
| I8088 | 3 | 0 | 0 | 0 | 0 | 0 |
| I80286 | 3 | 0 | 0 | 2 | 2 | 2 |
| Z80 | 3 | 0 | 0 | 0 | 1 | 0 |
| MC68000 | 3 | 1 | 1 | 1 | 2 | 1 |
| 2N3055 | 3 | 0 | 0 | 3 | 3 | 3 |
| MAX232 | 3 | 0 | 0 | 2 | 2 | 2 |
| ULN2003 | 1 | 0 | 0 | 0 | 0 | 0 |
| ESP8266 | 3 | 0 | 0 | 2 | 2 | 2 |
| ESP32 | 2 | 0 | 0 | 2 | 1 | 2 |
| mean over parts | | 4% | 4% | 34% | 37% | 34% |

## Look-alike families

| Family | Parts | Queries | image top-1 | image wrong, same family | fused top-1 | fused wrong, same family |
|---|---|---|---|---|---|---|
| 8-pin analog | NE555, UA741 | 6 | 3 | 1 | 4 | 0 |
| AVR ATmega | ATMEGA328P, ATMEGA8 | 4 | 1 | 0 | 1 | 0 |
| 3-pin regulators | LM7805, LM317 | 5 | 0 | 0 | 0 | 0 |
| Intel 8080-80286 | I8080, I8085, I8086, I8088, I80286 | 11 | 3 | 8 | 3 | 8 |
| Espressif Wi-Fi | ESP8266, ESP32 | 5 | 4 | 1 | 3 | 1 |

## Notes

- OCR read the correct part number: 5% of all queries, 5% of legible ones.
- Identifier channel fired on 2 queries; its top-1 was right 100% of the time.
- 2 legible queries carry a marking the catalog does not cover (I8088 `P80C88A-2`, UA741 `741P`): a perfect read would match none of the part's aliases exactly or glyph-folded (an alias shorter than 4 characters, such as `741`, never counts inside a longer word), or another part would match it better. On the other 41 legible queries OCR read the part number 5% of the time.
- 0 queries share the author of their own part's reference photo (a different session). Without them: image top-1 39% (17/44), fused top-1 43% (19/44).
- 2 queries are by the photographer of another part's reference photo, which can pull the image channel toward that part: 6691932.jpg (I8080; photographer of the I8086/I8088 reference), 8041354.jpg (MC68000; photographer of the I8086/I8088 reference). Without them: image top-1 40% (17/42), fused top-1 43% (18/42).

## Latency per query (ms, warm: second pass over the same photos)

| Stage | n | p50 | p95 | mean | first-pass mean |
|---|---|---|---|---|---|
| ocr | 44 | 94 | 168 | 107 | 108 |
| identifier | 44 | 0 | 1 | 0 | 0 |
| text | 10 | 9 | 10 | 10 | 10 |
| image | 44 | 28 | 32 | 28 | 28 |
| fusion | 44 | 0 | 0 | 0 | 0 |
| total | 44 | 124 | 197 | 137 | 138 |

The text stage only counts queries where the channel ran; it abstains when OCR finds no token of 3 or more letters or digits.

## Fused top-1 misses (25)

| Query | Truth | Fused top-3 | OCR text |
|---|---|---|---|
| 75189907.jpg | ATMEGA328P | LM317, ULN2003, ATMEGA8 | (none) |
| 133222141.jpg | ATMEGA328P | I80286, ESP32, ULN2003 | o |
| 74561381.jpg | ATMEGA8 | I80286, ATMEGA328P, MAX232 | 4 |
| 74560838.jpg | ESP32 | ESP8266, ESP32, NE555 | SPp cy Say |
| 56733450.jpg | ESP8266 | MAX232, I80286, ULN2003 | 206-0008: di 20 30 |
| 46635176.jpg | I80286 | I8080, I80286, I8088 | S 7 Za |
| 6691932.jpg | I8080 | I8088, I8086, I80286 | (none) |
| 55534764.jpg | I8080 | I8086, Z80, I8088 | (none) |
| 55534910.jpg | I8085 | I8086, ATMEGA328P, I80286 | (none) |
| 55534917.jpg | I8086 | I80286, I8086, I8088 | 86 |
| 55534991.jpg | I8088 | I8086, I8088, I80286 | (none) |
| 66104581.jpg | I8088 | I8085, ATMEGA328P, I8088 | 988 97 OIN |
| 78876305.jpg | I8088 | I8085, I80286, ATMEGA328P | 5 is |
| 23636678.jpg | LM317 | ULN2003, LM317, I80286 | & = |
| 74886172.jpg | LM317 | ULN2003, ATMEGA328P, Z80 | ain” |
| 75704312.jpg | LM317 | ULN2003, LM317, ESP32 | » 20 « |
| 177751130.jpg | LM7805 | ULN2003, LM317, I80286 | (none) |
| 194982655.jpg | LM7805 | ULN2003, LM317, I80286 | ce 49 |
| 178879707.jpg | MAX232 | ULN2003, ESP32, I80286 | i |
| 6976161.jpg | MC68000 | I8080, I80286, MC68000 | (none) |
| 20729665.jpg | NE555 | LM7805, NE555, MAX232 | (none) |
| 64573796.jpg | UA741 | ATMEGA8, ATMEGA328P, MAX232 | = |
| 126915852.jpg | ULN2003 | MAX232, ATMEGA328P, LM7805 | (none) |
| 55550822.jpg | Z80 | I8086, ATMEGA328P, ATMEGA8 | (none) |
| 59595187.jpg | Z80 | ESP32, ULN2003, ATMEGA328P | es |
