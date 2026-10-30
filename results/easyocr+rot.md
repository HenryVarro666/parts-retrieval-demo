# Run `easyocr+rot` (2026-10-30)

- Device: mps (Apple GPU); models loaded in 2.6 s
- Models: image `google/siglip-base-patch16-224` (revision `7fd15f0`), text `BAAI/bge-small-en-v1.5` (revision `5c38ec7`), OCR `easyocr+rot`
- Catalog: 18 parts; 18 have a reference photo (18 photos), so the image channel can only rank those. No photo: none.
- Queries: 44 photos of 18 parts (43 with a legible part marking). Parts with a reference photo but no query: none.

## Accuracy (all queries)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 25% (11/44) | 15-39% | 25% (11/44) | 15-39% | 0.25 | 27% |
| text | 34% (15/44) | 22-49% | 48% (21/44) | 34-62% | 0.45 | 82% |
| image | 39% (17/44) | 26-53% | 61% (27/44) | 47-74% | 0.54 | 100% |
| fused | 57% (25/44) | 42-70% | 73% (32/44) | 58-84% | 0.68 | 100% |
| fused_no_text | 50% (22/44) | 36-64% | 75% (33/44) | 61-85% | 0.66 | 100% |
| chance, 18 parts | 6% | | 17% | | 0.16 | |

`fused` is the pipeline: identifier (strong hits only, when there are any), text and image channels combined with reciprocal rank fusion. `fused_no_text` is an ablation without the text channel. Queries cluster by part (up to 3 per part), so the Wilson intervals are, if anything, too narrow.

## Accuracy (queries with a legible part marking)

| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |
|---|---|---|---|---|---|---|
| identifier | 26% (11/43) | 15-40% | 26% (11/43) | 15-40% | 0.26 | 28% |
| text | 35% (15/43) | 22-50% | 49% (21/43) | 35-63% | 0.46 | 84% |
| image | 40% (17/43) | 26-54% | 63% (27/43) | 48-76% | 0.55 | 100% |
| fused | 58% (25/43) | 43-72% | 74% (32/43) | 60-85% | 0.69 | 100% |
| fused_no_text | 51% (22/43) | 37-65% | 77% (33/43) | 62-87% | 0.67 | 100% |

## Paired top-1 comparisons

| Comparison | fused right, other wrong | other right, fused wrong | p (queries) | parts fused better | parts other better | p (parts) |
|---|---|---|---|---|---|---|
| fused vs identifier | 14 | 0 | <0.001 | 8 | 0 | 0.008 |
| fused vs text | 11 | 1 | 0.006 | 8 | 1 | 0.04 |
| fused vs image | 11 | 3 | 0.06 | 6 | 1 | 0.12 |
| fused vs fused_no_text | 6 | 3 | 0.51 | 3 | 2 | 1.00 |

Exact two-sided sign tests. The per-query test treats the queries of one part as independent, which they are not; the per-part test counts each part once and is the safer reading.

## Top-1 per part

| Part | Queries | identifier | text | image | fused | fused_no_text |
|---|---|---|---|---|---|---|
| NE555 | 3 | 2 | 0 | 2 | 2 | 2 |
| UA741 | 3 | 1 | 2 | 1 | 2 | 1 |
| ATMEGA328P | 3 | 1 | 1 | 1 | 1 | 1 |
| ATMEGA8 | 1 | 1 | 1 | 0 | 1 | 1 |
| LM7805 | 2 | 0 | 0 | 0 | 0 | 0 |
| LM317 | 3 | 0 | 1 | 0 | 2 | 0 |
| I8080 | 2 | 0 | 0 | 0 | 0 | 0 |
| I8085 | 1 | 0 | 0 | 0 | 0 | 0 |
| I8086 | 2 | 0 | 0 | 1 | 1 | 1 |
| I8088 | 3 | 0 | 1 | 0 | 0 | 0 |
| I80286 | 3 | 1 | 0 | 2 | 2 | 3 |
| Z80 | 3 | 2 | 2 | 0 | 2 | 2 |
| MC68000 | 3 | 1 | 1 | 1 | 3 | 1 |
| 2N3055 | 3 | 0 | 2 | 3 | 3 | 3 |
| MAX232 | 3 | 1 | 2 | 2 | 3 | 3 |
| ULN2003 | 1 | 0 | 0 | 0 | 0 | 0 |
| ESP8266 | 3 | 0 | 1 | 2 | 2 | 2 |
| ESP32 | 2 | 1 | 1 | 2 | 1 | 2 |
| mean over parts | | 25% | 32% | 34% | 52% | 47% |

## Look-alike families

| Family | Parts | Queries | image top-1 | image wrong, same family | fused top-1 | fused wrong, same family |
|---|---|---|---|---|---|---|
| 8-pin analog | NE555, UA741 | 6 | 3 | 1 | 4 | 0 |
| AVR ATmega | ATMEGA328P, ATMEGA8 | 4 | 1 | 0 | 2 | 0 |
| 3-pin regulators | LM7805, LM317 | 5 | 0 | 0 | 2 | 0 |
| Intel 8080-80286 | I8080, I8085, I8086, I8088, I80286 | 11 | 3 | 8 | 3 | 7 |
| Espressif Wi-Fi | ESP8266, ESP32 | 5 | 4 | 1 | 3 | 0 |

## Notes

- OCR read the correct part number: 23% of all queries, 23% of legible ones.
- Identifier channel fired on 12 queries; its top-1 was right 92% of the time.
- 2 legible queries carry a marking the catalog does not cover (I8088 `P80C88A-2`, UA741 `741P`): a perfect read would match none of the part's aliases exactly or glyph-folded (an alias shorter than 4 characters, such as `741`, never counts inside a longer word), or another part would match it better. On the other 41 legible queries OCR read the part number 24% of the time.
- 0 queries share the author of their own part's reference photo (a different session). Without them: image top-1 39% (17/44), fused top-1 57% (25/44).
- 2 queries are by the photographer of another part's reference photo, which can pull the image channel toward that part: 6691932.jpg (I8080; photographer of the I8086/I8088 reference), 8041354.jpg (MC68000; photographer of the I8086/I8088 reference). Without them: image top-1 40% (17/42), fused top-1 57% (24/42).

## Latency per query (ms, warm: second pass over the same photos)

| Stage | n | p50 | p95 | mean | first-pass mean |
|---|---|---|---|---|---|
| ocr | 44 | 164 | 572 | 221 | 260 |
| identifier | 44 | 1 | 2 | 1 | 1 |
| text | 36 | 5 | 6 | 5 | 5 |
| image | 44 | 16 | 19 | 16 | 16 |
| fusion | 44 | 0 | 0 | 0 | 0 |
| total | 44 | 185 | 605 | 242 | 282 |

The text stage only counts queries where the channel ran; it abstains when OCR finds no token of 3 or more letters or digits.

## Fused top-1 misses (19)

| Query | Truth | Fused top-3 | OCR text |
|---|---|---|---|
| 75189907.jpg | ATMEGA328P | LM317, ULN2003, ATMEGA8 | C |
| 133222141.jpg | ATMEGA328P | I80286, ESP32, ULN2003 | 4 |
| 97701682.jpg | ESP32 | ULN2003, Z80, ESP8266 | 8 5 048 23 Ozz 1 19 2 1 262020 1 33 32 8 3 3 dn |
| 54458803.jpg | ESP8266 | ULN2003, LM7805, I80286 | 5 3 8 8 9 8 4 1 & 2 4 0 2 3 Ablgl 4 1 6 RXD 5783 4 8 6P104 8 |
| 6976587.jpg | I80286 | I8085, UA741, NE555 | 01-98208Ve 1s5288670 8 5 8 |
| 6691932.jpg | I8080 | ATMEGA328P, I8088, I80286 | 28888657 3 "74 |
| 55534764.jpg | I8080 | I8088, ATMEGA328P, ATMEGA8 | 0808 €82 [-8 2 |
| 55534910.jpg | I8085 | I8088, I80286, I8085 | 2 0 45778' 0 |
| 55534917.jpg | I8086 | I8088, I8086, I80286 | 1 52864 2 78 |
| 55534991.jpg | I8088 | I80286, I8086, I8088 | 8 3 12020009 INTEL' |
| 66104581.jpg | I8088 | I8085, I80286, MAX232 | E 107 78 18 9 |
| 78876305.jpg | I8088 | I8085, I8088, I80286 | PBOC88A 2 INTEL78 0 027030J2 JAPAN |
| 23636678.jpg | LM317 | ULN2003, LM317, I80286 | 9 8 3 |
| 177751130.jpg | LM7805 | ULN2003, LM7805, NE555 | 0 8 5 GCHN 813 9n |
| 194982655.jpg | LM7805 | NE555, ULN2003, LM317 | 5 0 am( COCAAJN 6 |
| 20729665.jpg | NE555 | MAX232, ATMEGA328P, NE555 | 60239335 716088 |
| 64573796.jpg | UA741 | MAX232, ATMEGA328P, ATMEGA8 | 2741P 3 |
| 126915852.jpg | ULN2003 | MAX232, ATMEGA328P, LM7805 | (none) |
| 55550822.jpg | Z80 | I8086, ATMEGA328P, ATMEGA8 | l 0 |
