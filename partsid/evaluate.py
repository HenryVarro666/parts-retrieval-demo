"""Run the pipeline over the labelled query photos; report accuracy per channel and latency per stage.

    python -I -m partsid.evaluate --ocr easyocr
    python -I -m partsid.evaluate --ocr tesseract

Each run makes two passes over the queries. The first pays one-time costs (model
warm-up, kernel compilation for every new image size); the second is scored and
its timings are the reported warm latency. Writes results/<run>.md (summary),
results/<run>.json and results/<run>_per_query.csv.
"""
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # a few EasyOCR ops lack MPS kernels

import argparse
import csv
import datetime
import json
import math
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from . import identifier
from .catalog import CatalogIndex, part_document
from .device import describe, pick_device, synchronize
from .embed import DEFAULT_IMAGE_MODEL, DEFAULT_TEXT_MODEL, ImageEncoder, TextEncoder
from .fusion import rrf
from .images import load_rgb, orientation
from .ocr import make_engine

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
CHANNELS = ["identifier", "text", "image", "fused", "fused_no_text"]
STAGES = ["ocr", "identifier", "text", "image", "fusion", "total"]
MRR_DEPTH = 10  # one depth for every channel; fusion itself only sees each channel's top 10
_CONTENT = re.compile(r"[A-Za-z0-9]{3,}")  # OCR output without such a token is noise, not a query


def load_labels() -> tuple[list[dict], list[dict]]:
    with open(DATA / "labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["split"] == "catalog"], [r for r in rows if r["split"] == "query"]


def upright_path(rel: str) -> Path:
    """The photo itself, or an upright copy when it carries an EXIF rotation or an unreadable EXIF block.

    OCR engines read files and do not agree on EXIF handling (EasyOCR's detector
    and recogniser even load them differently), so every channel gets pixels that
    are already upright.
    """
    src = DATA / rel
    with Image.open(src) as im:
        if orientation(im) == 1:
            return src
    dst = DATA / "cache" / "upright" / rel
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        load_rgb(src).save(tmp, format="JPEG", quality=95)
        tmp.replace(dst)  # never leave a half-written copy for the next run to reuse
    return dst


def build_index(parts, catalog_rows, paths, text_enc, image_enc) -> CatalogIndex:
    text_vecs = text_enc.encode([part_document(p) for p in parts])
    images = [load_rgb(paths[r["file"]]) for r in catalog_rows]
    image_vecs = np.concatenate([image_enc.encode(images[i:i + 16]) for i in range(0, len(images), 16)])
    return CatalogIndex(parts, text_vecs, image_vecs, [r["part_id"] for r in catalog_rows])


class Pipeline:
    def __init__(self, parts, index, ocr, text_enc, image_enc, device):
        self.parts, self.index, self.ocr = parts, index, ocr
        self.text_enc, self.image_enc, self.device = text_enc, image_enc, device

    def _lap(self, t0: float) -> tuple[float, float]:
        synchronize(self.device)
        now = time.perf_counter()
        return (now - t0) * 1000, now

    def run(self, path: Path) -> dict:
        ms = {}
        start = t = time.perf_counter()
        text = self.ocr.read(path)
        ms["ocr"], t = self._lap(t)

        id_hits = identifier.rank(text, self.parts)
        ms["identifier"], t = self._lap(t)

        text_ranked, ms["text"] = [], None  # None: the channel abstained, no cost to report
        if _CONTENT.search(text):
            qv = self.text_enc.encode([text], is_query=True)[0]
            text_ranked = self.index.search_text(qv)
            ms["text"], t = self._lap(t)

        iv = self.image_enc.encode([load_rgb(path)])[0]
        image_ranked = self.index.search_image(iv)
        ms["image"], t = self._lap(t)

        rankings = {
            "identifier": [pid for pid, _, _ in id_hits],
            "text": [pid for pid, _ in text_ranked],
            "image": [pid for pid, _ in image_ranked],
        }
        strong_ids = identifier.for_fusion(id_hits)
        rankings["fused"] = [pid for pid, _ in rrf(
            {"identifier": strong_ids, "text": rankings["text"], "image": rankings["image"]})]
        # Ablation, not part of the pipeline: the same fusion without the text channel.
        rankings["fused_no_text"] = [pid for pid, _ in rrf({"identifier": strong_ids, "image": rankings["image"]})]
        ms["fusion"], t = self._lap(t)
        ms["total"] = (t - start) * 1000
        return {"ocr_text": text, "id_hits": id_hits, "rankings": rankings,
                "image_sims": dict(image_ranked), "ms": ms}


def _rank_of(gt: str, ranked: list[str]) -> int | None:
    return ranked.index(gt) + 1 if gt in ranked else None


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for k successes out of n."""
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, centre - half), min(1.0, centre + half)]


def sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test on paired outcomes; ties are dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2 ** n)


def chance(n_candidates: int) -> dict:
    """Uniform random ranking over n candidates."""
    harmonic = sum(1 / r for r in range(1, min(MRR_DEPTH, n_candidates) + 1))
    return {"top1": 1 / n_candidates, "top3": min(3, n_candidates) / n_candidates, "mrr": harmonic / n_candidates}


def accuracy(results: list[dict], channel: str) -> dict:
    ranks = [r["ranks"][channel] for r in results]
    n = len(ranks)
    k1 = sum(1 for x in ranks if x == 1)
    k3 = sum(1 for x in ranks if x and x <= 3)
    return {
        "n": n, "top1_k": k1, "top3_k": k3,
        "top1": k1 / n if n else None, "top3": k3 / n if n else None,
        "top1_ci95": wilson(k1, n), "top3_ci95": wilson(k3, n),
        "mrr": sum(1 / x for x in ranks if x and x <= MRR_DEPTH) / n if n else None,
        "coverage": sum(1 for r in results if r["rankings"][channel]) / n if n else None,
    }


def paired(results: list[dict], a: str, b: str) -> dict:
    """Top-1 of channel a against channel b on the same queries, counted per query and per part.

    Queries of one part are not independent, so the per-part count takes each
    part once: a win when a is right on more of its queries than b, a loss when
    on fewer.
    """
    def wins_losses(rs):
        return (sum(1 for r in rs if r["ranks"][a] == 1 and r["ranks"][b] != 1),
                sum(1 for r in rs if r["ranks"][a] != 1 and r["ranks"][b] == 1))

    wins, losses = wins_losses(results)
    by_part = defaultdict(list)
    for r in results:
        by_part[r["gt"]].append(r)
    diffs = [w - lo for w, lo in map(wins_losses, by_part.values())]
    part_wins, part_losses = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    return {"wins": wins, "losses": losses, "p_sign_test": sign_test(wins, losses),
            "part_wins": part_wins, "part_losses": part_losses,
            "p_sign_test_parts": sign_test(part_wins, part_losses)}


def _top1(r: dict, channel: str) -> str | None:
    return r["rankings"][channel][0] if r["rankings"][channel] else None


def per_part(results: list[dict], parts: list[dict]) -> list[dict]:
    rows = []
    for p in parts:
        rs = [r for r in results if r["gt"] == p["id"]]
        rows.append({"part": p["id"], "family": p.get("family", p["id"]), "n": len(rs),
                     **{c: sum(1 for r in rs if r["ranks"][c] == 1) for c in CHANNELS}})
    return rows


def mean_over_parts(rows: list[dict]) -> dict:
    """Top-1 averaged over parts with queries, so a part with 3 queries weighs as much as one with 1."""
    with_q = [row for row in rows if row["n"]]
    return {c: statistics.fmean(row[c] / row["n"] for row in with_q) for c in CHANNELS} if with_q else {}


def families(results: list[dict], parts: list[dict]) -> list[dict]:
    """Look-alike families (parts.json "family"): how often a wrong top-1 is another member of the same family."""
    family_of = {p["id"]: p.get("family", p["id"]) for p in parts}
    members = defaultdict(list)
    for p in parts:
        members[family_of[p["id"]]].append(p["id"])
    out = []
    for fam, ids in members.items():
        if len(ids) < 2:
            continue
        rs = [r for r in results if r["gt"] in ids]
        row = {"family": fam, "parts": ids, "n": len(rs)}
        for c in ("image", "fused"):
            row[f"{c}_top1"] = sum(1 for r in rs if r["ranks"][c] == 1)
            row[f"{c}_wrong_in_family"] = sum(
                1 for r in rs if r["ranks"][c] != 1 and family_of.get(_top1(r, c)) == fam)
        out.append(row)
    return out


def latency(ms_list: list[dict]) -> dict:
    out = {}
    for stage in STAGES:
        vals = sorted(m[stage] for m in ms_list if m[stage] is not None)
        if not vals:
            out[stage] = None
            continue
        p95 = statistics.quantiles(vals, n=20, method="inclusive")[18] if len(vals) > 1 else vals[0]
        out[stage] = {"n": len(vals), "p50": statistics.median(vals), "p95": p95, "mean": statistics.fmean(vals)}
    return out


def _author(artist: str) -> str:
    return " ".join(artist.casefold().split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", default="easyocr", choices=["easyocr", "easyocr+rot", "tesseract"])
    ap.add_argument("--device", default=None, help="cuda / mps / cpu; default picks the best available")
    ap.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    ap.add_argument("--text-model", default=DEFAULT_TEXT_MODEL)
    ap.add_argument("--run-name", default=None)
    args = ap.parse_args()

    device = pick_device(args.device)
    parts = json.loads((DATA / "parts.json").read_text(encoding="utf-8"))
    catalog_rows, queries = load_labels()
    with_photo = {r["part_id"] for r in catalog_rows}
    paths = {r["file"]: upright_path(r["file"]) for r in catalog_rows + queries}

    t0 = time.perf_counter()
    image_enc = ImageEncoder(device, args.image_model)
    text_enc = TextEncoder(device, args.text_model)
    ocr = make_engine(args.ocr, device)
    load_s = time.perf_counter() - t0
    # Every catalog part takes part in the identifier and text channels; the image
    # channel can only rank parts that have a reference photo.
    index = build_index(parts, catalog_rows, paths, text_enc, image_enc)
    pipe = Pipeline(parts, index, ocr, text_enc, image_enc, device)
    aliases = {p["id"]: p["aliases"] for p in parts}
    ref_author = {r["part_id"]: _author(r["artist"]) for r in catalog_rows}
    ref_parts_of_author = defaultdict(set)
    for pid, a in ref_author.items():
        if a:
            ref_parts_of_author[a].add(pid)

    first_pass = [pipe.run(paths[q["file"]])["ms"] for q in queries]
    results = []
    for q in queries:
        r = pipe.run(paths[q["file"]])
        gt = q["part_id"]
        author = _author(q["artist"])
        r.update(file=q["file"], gt=gt, legible=q["marking_legible"],
                 marking=q.get("marking", ""), marking_in_catalog=q.get("marking_in_catalog", "") == "y",
                 same_author=bool(author) and author == ref_author.get(gt),
                 # Another part's reference photo is by the same photographer: possibly the same
                 # session, which pulls the image channel toward that part.
                 cross_author=sorted(ref_parts_of_author.get(author, set()) - {gt}) if author else [])
        r["ranks"] = {c: _rank_of(gt, r["rankings"][c]) for c in CHANNELS}
        r["ocr_hit"] = identifier.score_part(r["ocr_text"], aliases[gt])[0] >= identifier.FOLDED
        r["image_gt_sim"] = r["image_sims"].get(gt)
        r["image_top"] = max(r["image_sims"].items(), key=lambda kv: kv[1])
        results.append(r)

    run = args.run_name or args.ocr
    fired = [r for r in results if r["rankings"]["identifier"]]
    legible = [r for r in results if r["legible"] == "y"]
    covered = [r for r in legible if r["marking_in_catalog"]]
    other_author = [r for r in results if not r["same_author"]]
    no_cross = [r for r in results if not r["cross_author"]]
    part_rows = per_part(results, parts)
    summary = {
        "run": run,
        "date": datetime.date.today().isoformat(),
        "device": describe(device),
        "models": {"image": args.image_model, "image_revision": image_enc.revision,
                   "text": args.text_model, "text_revision": text_enc.revision, "ocr": ocr.name},
        "model_load_s": load_s,
        "n_parts": len(parts), "n_parts_with_photo": len(with_photo),
        "parts_without_photo": sorted(p["id"] for p in parts if p["id"] not in with_photo),
        "parts_with_queries": sorted({q["part_id"] for q in queries}),
        "parts_without_queries": sorted(with_photo - {q["part_id"] for q in queries}),
        "n_catalog_images": len(catalog_rows), "n_queries": len(results), "n_legible": len(legible),
        "chance": {"all_parts": chance(len(parts)), "parts_with_photo": chance(len(with_photo))},
        "accuracy": {c: accuracy(results, c) for c in CHANNELS},
        "accuracy_legible": {c: accuracy(legible, c) for c in CHANNELS},
        "paired_top1": {f"fused_vs_{c}": paired(results, "fused", c)
                        for c in ("identifier", "text", "image", "fused_no_text")},
        "per_part": part_rows,
        "mean_over_parts_top1": mean_over_parts(part_rows),
        "families": families(results, parts),
        "n_same_author": len(results) - len(other_author),
        "accuracy_other_author": {c: accuracy(other_author, c) for c in ("image", "fused")},
        "cross_author": [{"file": r["file"], "part": r["gt"], "reference_of": r["cross_author"]}
                         for r in results if r["cross_author"]],
        "accuracy_without_cross_author": {c: accuracy(no_cross, c) for c in ("image", "fused")},
        "ocr_hit_rate": sum(r["ocr_hit"] for r in results) / len(results),
        "ocr_hit_rate_legible": (sum(r["ocr_hit"] for r in legible) / len(legible)) if legible else None,
        "markings_not_in_catalog": [{"file": r["file"], "part": r["gt"], "marking": r["marking"]}
                                    for r in legible if not r["marking_in_catalog"]],
        "ocr_hit_rate_catalog_covered": (sum(r["ocr_hit"] for r in covered) / len(covered)) if covered else None,
        "n_catalog_covered": len(covered),
        "identifier_fired": len(fired),
        "identifier_precision_when_fired": (sum(r["ranks"]["identifier"] == 1 for r in fired) / len(fired)) if fired else None,
        "latency_ms": latency([r["ms"] for r in results]),
        "latency_ms_first_pass": latency(first_pass),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{run}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(RESULTS / f"{run}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "gt", "legible", "marking_in_catalog", "same_author", "cross_author", "ocr_hit",
                    *(f"rank_{c}" for c in CHANNELS), "fused_top3", "image_gt_sim", "image_top_part",
                    "image_top_sim", "total_ms", "ocr_text"])
        for r in results:
            w.writerow([r["file"], r["gt"], r["legible"], int(r["marking_in_catalog"]), int(r["same_author"]),
                        " ".join(r["cross_author"]), int(r["ocr_hit"]),
                        *(r["ranks"][c] or "" for c in CHANNELS),
                        " ".join(r["rankings"]["fused"][:3]),
                        "" if r["image_gt_sim"] is None else f"{r['image_gt_sim']:.3f}",
                        r["image_top"][0], f"{r['image_top'][1]:.3f}", f"{r['ms']['total']:.0f}", r["ocr_text"][:120]])
    md = render_markdown(summary, results)
    (RESULTS / f"{run}.md").write_text(md, encoding="utf-8")
    print(md)


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _ci(ci) -> str:
    return "n/a" if ci is None else f"{100 * ci[0]:.0f}-{100 * ci[1]:.0f}%"


def _p(p: float) -> str:
    """An exact sign test is never 0, so small values are shown as a bound, not rounded away."""
    return "<0.001" if p < 0.001 else f"{p:.3f}" if p < 0.01 else f"{p:.2f}"


def _acc_rows(acc: dict, channels: list[str]) -> list[str]:
    rows = []
    for c in channels:
        a = acc[c]
        if not a["n"]:
            continue
        rows.append(f"| {c} | {_pct(a['top1'])} ({a['top1_k']}/{a['n']}) | {_ci(a['top1_ci95'])} "
                    f"| {_pct(a['top3'])} ({a['top3_k']}/{a['n']}) | {_ci(a['top3_ci95'])} "
                    f"| {a['mrr']:.2f} | {_pct(a['coverage'])} |")
    return rows


def render_markdown(s: dict, results: list[dict]) -> str:
    head = ("| Channel | Top-1 | Top-1 95% CI | Top-3 | Top-3 95% CI | MRR@10 | Coverage |\n"
            "|---|---|---|---|---|---|---|")
    ch_all, ch_img = s["chance"]["all_parts"], s["chance"]["parts_with_photo"]
    chance_rows = [f"| chance, {s['n_parts']} parts | {_pct(ch_all['top1'])} | | {_pct(ch_all['top3'])} | "
                   f"| {ch_all['mrr']:.2f} | |"]
    if s["n_parts_with_photo"] != s["n_parts"]:
        chance_rows.append(f"| chance, {s['n_parts_with_photo']} parts (image) | {_pct(ch_img['top1'])} | "
                           f"| {_pct(ch_img['top3'])} | | {ch_img['mrr']:.2f} | |")
    lines = [
        f"# Run `{s['run']}` ({s['date']})",
        "",
        f"- Device: {s['device']}; models loaded in {s['model_load_s']:.1f} s",
        f"- Models: image `{s['models']['image']}` (revision `{s['models']['image_revision'][:7]}`), "
        f"text `{s['models']['text']}` (revision `{s['models']['text_revision'][:7]}`), OCR `{s['models']['ocr']}`",
        f"- Catalog: {s['n_parts']} parts; {s['n_parts_with_photo']} have a reference photo "
        f"({s['n_catalog_images']} photos), so the image channel can only rank those. "
        f"No photo: {', '.join(s['parts_without_photo']) or 'none'}.",
        f"- Queries: {s['n_queries']} photos of {len(s['parts_with_queries'])} parts "
        f"({s['n_legible']} with a legible part marking). "
        f"Parts with a reference photo but no query: {', '.join(s['parts_without_queries']) or 'none'}.",
        "",
        "## Accuracy (all queries)",
        "",
        head,
        *_acc_rows(s["accuracy"], CHANNELS),
        *chance_rows,
        "",
        "`fused` is the pipeline: identifier (strong hits only, when there are any), text and image channels "
        "combined with reciprocal rank fusion. `fused_no_text` is an ablation without the text channel. "
        "Queries cluster by part (up to 3 per part), so the Wilson intervals are, if anything, too narrow.",
    ]
    if s["accuracy_legible"]["fused"]["n"]:
        lines += ["", "## Accuracy (queries with a legible part marking)", "", head,
                  *_acc_rows(s["accuracy_legible"], CHANNELS)]
    lines += ["", "## Paired top-1 comparisons", "",
              "| Comparison | fused right, other wrong | other right, fused wrong | p (queries) "
              "| parts fused better | parts other better | p (parts) |",
              "|---|---|---|---|---|---|---|"]
    for name, p in s["paired_top1"].items():
        lines.append(f"| {name.replace('_vs_', ' vs ')} | {p['wins']} | {p['losses']} | {_p(p['p_sign_test'])} "
                     f"| {p['part_wins']} | {p['part_losses']} | {_p(p['p_sign_test_parts'])} |")
    lines += ["", "Exact two-sided sign tests. The per-query test treats the queries of one part as independent, "
              "which they are not; the per-part test counts each part once and is the safer reading."]

    lines += ["", "## Top-1 per part", "",
              "| Part | Queries | " + " | ".join(CHANNELS) + " |",
              "|---|---|" + "---|" * len(CHANNELS)]
    for row in s["per_part"]:
        if row["n"]:
            lines.append(f"| {row['part']} | {row['n']} | " + " | ".join(str(row[c]) for c in CHANNELS) + " |")
    if s["mean_over_parts_top1"]:
        lines.append("| mean over parts | | " + " | ".join(_pct(s["mean_over_parts_top1"][c]) for c in CHANNELS) + " |")

    if s["families"]:
        lines += ["", "## Look-alike families", "",
                  "| Family | Parts | Queries | image top-1 | image wrong, same family | fused top-1 "
                  "| fused wrong, same family |", "|---|---|---|---|---|---|---|"]
        for f in s["families"]:
            lines.append(f"| {f['family']} | {', '.join(f['parts'])} | {f['n']} | {f['image_top1']} "
                         f"| {f['image_wrong_in_family']} | {f['fused_top1']} | {f['fused_wrong_in_family']} |")

    oa, nc = s["accuracy_other_author"], s["accuracy_without_cross_author"]
    lines += [
        "",
        "## Notes",
        "",
        f"- OCR read the correct part number: {_pct(s['ocr_hit_rate'])} of all queries, "
        f"{_pct(s['ocr_hit_rate_legible'])} of legible ones.",
        f"- Identifier channel fired on {s['identifier_fired']} queries; its top-1 was right "
        f"{_pct(s['identifier_precision_when_fired'])} of the time.",
    ]
    if s["markings_not_in_catalog"]:
        gaps = ", ".join(f"{m['part']} `{m['marking']}`" for m in s["markings_not_in_catalog"])
        lines.append(f"- {len(s['markings_not_in_catalog'])} legible queries carry a marking the catalog does not "
                     f"cover ({gaps}): a perfect read would match none of the part's aliases exactly or "
                     f"glyph-folded (an alias shorter than 4 characters, such as `741`, never counts inside a "
                     f"longer word), or another part would match it better. "
                     f"On the other {s['n_catalog_covered']} legible queries OCR read the part number "
                     f"{_pct(s['ocr_hit_rate_catalog_covered'])} of the time.")
    lines.append(f"- {s['n_same_author']} queries share the author of their own part's reference photo "
                 f"(a different session). Without them: image top-1 {_pct(oa['image']['top1'])} "
                 f"({oa['image']['top1_k']}/{oa['image']['n']}), fused top-1 {_pct(oa['fused']['top1'])} "
                 f"({oa['fused']['top1_k']}/{oa['fused']['n']}).")
    if s["cross_author"]:
        names = ", ".join(f"{Path(c['file']).name} ({c['part']}; photographer of the {'/'.join(c['reference_of'])} "
                          f"reference)" for c in s["cross_author"])
        lines.append(f"- {len(s['cross_author'])} queries are by the photographer of another part's reference photo, "
                     f"which can pull the image channel toward that part: {names}. Without them: image top-1 "
                     f"{_pct(nc['image']['top1'])} ({nc['image']['top1_k']}/{nc['image']['n']}), fused top-1 "
                     f"{_pct(nc['fused']['top1'])} ({nc['fused']['top1_k']}/{nc['fused']['n']}).")
    else:
        lines.append("- No query is by the photographer of another part's reference photo.")
    lines += [
        "",
        "## Latency per query (ms, warm: second pass over the same photos)",
        "",
        "| Stage | n | p50 | p95 | mean | first-pass mean |",
        "|---|---|---|---|---|---|",
    ]
    for stage in STAGES:
        lw, lc = s["latency_ms"][stage], s["latency_ms_first_pass"][stage]
        if lw is None:
            lines.append(f"| {stage} | 0 | | | | |")
            continue
        lines.append(f"| {stage} | {lw['n']} | {lw['p50']:.0f} | {lw['p95']:.0f} | {lw['mean']:.0f} "
                     f"| {lc['mean']:.0f} |")
    lines += ["", "The text stage only counts queries where the channel ran; it abstains when OCR finds no "
              "token of 3 or more letters or digits."]
    misses = [r for r in results if r["ranks"]["fused"] != 1]
    lines += ["", f"## Fused top-1 misses ({len(misses)})", "",
              "| Query | Truth | Fused top-3 | OCR text |", "|---|---|---|---|"]
    for r in misses:
        ocr_text = r["ocr_text"][:60].replace("|", "/") or "(none)"
        lines.append(f"| {Path(r['file']).name} | {r['gt']} | {', '.join(r['rankings']['fused'][:3])} | {ocr_text} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
