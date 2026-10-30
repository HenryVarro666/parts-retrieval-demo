# How data/curation.csv was labelled

The labels were made by Claude vision subagents (Claude Code workflow runs on 2026-10-30), not by a domain expert.

- Per part, two labellers, A and B, judged every downloaded photo independently. Each opened every image file; B saw the photos in reverse order. Both got the part's name, aliases and makers, the photo's Commons title and author, and the rules below.
- A photo where A and B disagreed on `keep`, or on `marking_legible` for a kept photo, went to a third labeller who saw both answers and the image. That happened twice. One of the two photos (LM317 14784539) was later labelled again from a larger file, with A and B agreeing, so `decided_by` is `tiebreak` on one row only (ATMEGA328P 133222141).
- `group` is the union of A's and B's groupings: two kept photos share a group if either labeller put them together. Photos labelled in a later round were grouped against the photos already kept, and earlier groups kept their members. After the last round each part's groups were renumbered g1, g2, ... in page-id order of their first photo, so the ids can differ from the ones the labellers saw or wrote. The notes keep the ids of the round they were written in, and six of them name groups whose ids have since changed. Four say the photo belongs with a group, and that group is now the photo's own: Z80 55550822, ATMEGA8 74561381 and 74561382, and ESP32 117048431. Two say the photo differs from other groups: on UA741 68626041 the old g3 is today's g4, and on LM317 75704312 the old g2 and g3 are today's g3 and g5. The `group` column is authoritative.
- A photo was labelled again whenever its stored size changed, for example when a 330 px rendition was replaced by the 960 px one. Two files were downloaded again at the same size and not labelled again: NE555 20729665, a query (the same picture re-encoded; `NE555N` reads the same), and NE555 27608793, which was dropped. `judged_size` is the size of the file the labels describe. `partsid.make_labels` stops when a curation row has none, and warns when the size that `manifest.csv` records for any curated file, kept or dropped, differs from it. It does not open the photos; `fetch_commons --from-manifest` is what checks the files on disk against the manifest. A file replaced by another of the same size goes unnoticed.

| Round | Photos | Agreement on keep | Agreement on legible (both kept) | Tie-breaks |
|---|---|---|---|---|
| 1 | 122 | 121/122 | 39/39 | 1 |
| 2 | 100 (87 new, 13 re-downloaded) | 100/100 | 56/57 | 1 |
| 3 | 10 (re-downloaded) | 10/10 | 3/3 | 0 |

## The rules, as given to every labeller

Decide for EACH photo:

keep = "y" only if ALL of these hold, otherwise "n":

1. It is a photograph. Not a drawing, render, diagram, schematic, pinout, waveform, datasheet scan, die shot, decapped chip, micrograph or X-ray.
2. The main subject is one or more packaged units of THIS catalog part: the part fills a large share of the frame and is the obvious focus. A circuit board, breadboard, kit, development board or finished device where the part is one component among many is "n", even when the part is visible on it. Several different part numbers side by side is "n". Several units of the same part is fine.
3. The unit really is this catalog part: its marking (or, when no marking is readable, the photo title) names this part's base number, with any maker prefix or suffix, speed grade, package or CMOS variant (examples: KA555, TL7805CV, AM8086, MC68HC000, Z84C00, 80C286, ATmega8L, ESP-12F module for the ESP8266). A chip sold under a DIFFERENT part number is "n" even when it is a functional clone or a licensed second source (examples: U880 or uPD780C for the Z80, KR580VM80A for the 8080, ST232 for the MAX232). A photo whose visible marking names a different catalog part (e.g. an 8085 in the 8080 category) is "n".

The image decides, not the title: if the title says one thing and the photo clearly shows another, follow the photo.

marking_legible = "y" if a person looking at this image as stored can read this part's base number in the unit's marking (the logo or a date code alone is not enough); "n" if the marking is absent, too small, blurred, washed out by glare, facing away or cut off. Give it for every photo; for dropped photos it is not used.

marking = the part-number text you can actually read on the unit, copied as printed (e.g. "NE555P", "P8086", "MC68000L8"); "" if none is readable. Do not fill it in from the title.

group = for kept photos only: photos showing the SAME physical unit, or from the same photo session (same author with the same background, lighting and object arrangement), share a group letter; unrelated photos get different letters. Use "a", "b", "c", ... in order of first appearance among kept photos. Use "-" for dropped photos.

note = one short phrase: what the photo shows, or why it is dropped.
