"""Turn the curation into labels.csv with a fixed, non-cherry-picked split.

data/curation.csv holds one row per downloaded photo: part_id, pageid, keep (y/n),
marking_legible (y/n), marking, group, judged_size, note. `group` ties together kept
photos of the same physical unit or the same photo session. For each part the kept
photos are sorted by Commons page id. The first becomes the catalog reference
photo. Queries are the next photos whose group is not used yet, so never the
reference's own session and at most one per session, up to MAX_QUERIES. A part
whose kept photos all come from one session stays in the catalog as a distractor
with no queries.

A file that manifest.csv lists under several parts (e.g. a museum case of Intel
CPUs) is excluded by rule, whatever its curation says.

Checks that stop or warn before an eval runs on labels that no longer fit:
- a kept photo missing from manifest.csv stops the run, since the split would
  silently shift (the next photo would become the reference);
- a curation row without `judged_size`, the size the labellers looked at, stops
  the run, and any curated file (kept or dropped) whose size in manifest.csv
  differs from it is listed: its keep and legibility labels may not hold. The
  photos themselves are not opened (fetch_commons --from-manifest checks them
  against the manifest), and a file replaced by another of the same size is not
  caught;
- a legible marking the catalog does not cover is listed and written to
  labels.csv (`marking_in_catalog` = n), so a catalog gap is not read as an OCR
  miss. Covered means a perfect read would match one of the part's own aliases
  exactly or glyph-folded under the identifier's rules (an alias shorter than 4
  characters, such as 741, never inside a longer word) and no other part better.

    python -I -m partsid.make_labels
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

from . import identifier

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAX_QUERIES = 3


def split(kept: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    """(reference, queries, unused) for one part's kept curation rows."""
    rows = sorted(kept, key=lambda c: int(c["pageid"]))
    ref, queries, unused = rows[0], [], []
    used_groups = {ref["group"]}
    for c in rows[1:]:
        if c["group"] in used_groups or len(queries) == MAX_QUERIES:
            unused.append(c)
        else:
            queries.append(c)
            used_groups.add(c["group"])
    return ref, queries, unused


def marking_in_catalog(marking: str, part_id: str, parts: list[dict]) -> bool:
    """Would a perfect read of this marking match one of the part's aliases exactly or
    glyph-folded (what evaluate counts as an OCR hit), and at least as well as any other part?"""
    scores = {p["id"]: identifier.score_part(marking, p["aliases"])[0] for p in parts}
    own = scores.pop(part_id)
    return own >= identifier.FOLDED and own >= max(scores.values(), default=0.0)


def main() -> None:
    parts = json.loads((DATA / "parts.json").read_text(encoding="utf-8"))
    with open(DATA / "manifest.csv", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    files = {(m["part_id"], m["pageid"]): m for m in manifest}
    parts_of = defaultdict(set)
    for m in manifest:
        parts_of[m["pageid"]].add(m["part_id"])
    multi = {pageid for pageid, pids in parts_of.items() if len(pids) > 1}

    with open(DATA / "curation.csv", encoding="utf-8") as f:
        curation = list(csv.DictReader(f))
    kept, seen, not_in_manifest, no_size, resized = defaultdict(list), set(), [], [], []
    for c in curation:
        key = (c["part_id"], c["pageid"])
        if key in seen:
            raise SystemExit(f"curation.csv lists {key} twice")
        seen.add(key)
        if key not in files:
            if c["keep"] == "y":
                not_in_manifest.append(key)
            continue
        m = files[key]
        stored = f"{m['stored_width']}x{m['stored_height']}"
        if not c.get("judged_size"):
            no_size.append(key)
        elif c["judged_size"] != stored:
            resized.append(f"{key[0]}/{key[1]} ({'kept' if c['keep'] == 'y' else 'dropped'}) "
                           f"judged at {c['judged_size']}, stored {stored}")
        if c["keep"] == "y" and c["pageid"] not in multi:
            if c["group"] in ("", "-"):
                raise SystemExit(f"kept photo {key} has no group")
            kept[c["part_id"]].append(c)
    if not_in_manifest:
        raise SystemExit(f"{len(not_in_manifest)} kept photos are missing from manifest.csv, e.g. "
                         f"{not_in_manifest[0]}; the split would shift. Rebuild the manifest first.")
    if no_size:
        raise SystemExit(f"{len(no_size)} curation rows have no judged_size, e.g. {no_size[0]}; "
                         "without it a re-sized file cannot be caught. Record the size each label was made on.")
    for pageid in sorted(multi, key=int):
        print(f"excluded {pageid}: filed under {', '.join(sorted(parts_of[pageid]))}")
    unlabelled = [key for key in files if key not in seen]
    if unlabelled:
        print(f"{len(unlabelled)} downloaded photos have no curation row, e.g. {unlabelled[0]}")

    rows, unused, gaps = [], [], []
    for part_id in sorted(kept):
        ref, queries, rest = split(kept[part_id])
        unused += rest
        for role, c in [("catalog", ref)] + [("query", q) for q in queries]:
            m = files[(part_id, c["pageid"])]
            covered = c["marking_legible"] == "y" and marking_in_catalog(c["marking"], part_id, parts)
            if c["marking_legible"] == "y" and not covered:
                gaps.append(f"{part_id}/{c['pageid']} ({role}) '{c['marking']}'")
            rows.append({
                "file": m["file"], "part_id": part_id, "split": role,
                "marking_legible": c["marking_legible"], "marking": c["marking"],
                "marking_in_catalog": "y" if covered else "n", "group": c["group"], "pageid": c["pageid"],
                "license": m["license"], "artist": m["artist"], "page_url": m["page_url"],
            })
    with open(DATA / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n_q = sum(r["split"] == "query" for r in rows)
    no_queries = sorted(p for p in kept if not any(r["part_id"] == p and r["split"] == "query" for r in rows))
    print(f"{len(kept)} parts with a kept photo: {len(rows) - n_q} catalog photos, {n_q} queries, "
          f"{len(unused)} kept photos unused (a session already used, or over {MAX_QUERIES} per part) "
          f"-> {DATA / 'labels.csv'}")
    if no_queries:
        print(f"catalog only, no queries: {', '.join(no_queries)}")
    if gaps:
        print(f"{len(gaps)} legible markings the catalog does not cover (marking_in_catalog = n): " + "; ".join(gaps))
    if resized:
        print(f"WARNING: {len(resized)} curated files differ in size from the file the labellers judged; "
              "re-label them before trusting the split: " + "; ".join(resized))


if __name__ == "__main__":
    main()
