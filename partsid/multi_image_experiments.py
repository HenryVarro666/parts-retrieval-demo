"""Paired same-object evaluation, kept separate from the historical 44 photos."""
import argparse
import csv
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from .candidate_pipeline import ROOT, sha256
from .multi_image import compare_paths, image_signature


def data_path(root, relative):
    if not isinstance(relative, str):
        raise ValueError("Invalid photo path")
    data = (Path(root) / "data").resolve()
    path = (data / relative).resolve()
    if not path.is_relative_to(data) or not path.is_file():
        raise ValueError("Photo must exist inside data/")
    return path


def load_manifest(path, root=ROOT):
    doc = json.loads(Path(path).read_text())
    scope = doc.get("scope")
    if doc.get("schema") != 1 or scope not in ("exploratory_same_object", "confirmed_same_object") or not doc.get("groups"):
        raise ValueError("Unknown paired manifest schema/scope")
    parts_path = Path(root) / "data/parts.json"
    part_ids = {p["id"] for p in json.loads(parts_path.read_text())} if parts_path.exists() else None
    with open(Path(root) / "data/labels.csv", encoding="utf-8") as f:
        catalog_paths = [data_path(root, r["file"]) for r in csv.DictReader(f) if r["split"] == "catalog"]
    catalog_pixels = {image_signature(p)["pixel_sha256"] for p in catalog_paths}
    seen = set()
    for group in doc["groups"]:
        identity = group.get("identity_basis", {})
        status = identity.get("status")
        oid = group.get("object_id")
        if not isinstance(oid, str) or not oid.strip() or oid in seen:
            raise ValueError("Object IDs must be unique")
        seen.add(oid)
        if not group.get("part_id") or (part_ids is not None and group["part_id"] not in part_ids):
            raise ValueError("Unknown evaluation model")
        if status not in ("user_confirmed", "source_documented", "visually_supported") or not str(identity.get("evidence", "")).strip():
            raise ValueError("Same-object grouping needs provenance evidence")
        if scope == "confirmed_same_object" and status == "visually_supported":
            raise ValueError("Visual inference is not confirmed physical identity")
        photos = group.get("photos")
        if not isinstance(photos, list) or len(photos) != 3:
            raise ValueError("Paired evaluation requires three photos")
        pixels = []
        for photo in photos:
            file = data_path(root, photo.get("file"))
            if photo.get("sha256") != sha256(file):
                raise ValueError("Stale photo hash")
            sig = image_signature(file)
            if sig["width"] * sig["height"] > 16_000_000 or file.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Photo exceeds upload budget")
            pixels.append(sig["pixel_sha256"])
            source = photo.get("source")
            if source:
                original = data_path(root, source.get("file"))
                if source.get("sha256") != sha256(original):
                    raise ValueError("Stale original hash")
                if original in catalog_paths:
                    raise ValueError("Paired source overlaps catalog")
                crop = source.get("crop")
                with Image.open(original) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    if (not isinstance(crop, list) or len(crop) != 4 or not all(type(v) is int for v in crop)
                            or not (0 <= crop[0] < crop[2] <= image.width and 0 <= crop[1] < crop[3] <= image.height)):
                        raise ValueError("Invalid source crop")
                    expected = image.crop(crop)
                with Image.open(file) as image:
                    actual = image.convert("RGB")
                    if expected.size != actual.size or expected.tobytes() != actual.tobytes():
                        raise ValueError("Derived photo differs from declared source crop")
        if len(set(pixels)) != 3:
            raise ValueError("Repeated pixels are not a true three-photo group")
        if catalog_pixels.intersection(pixels):
            raise ValueError("Paired queries overlap catalog")
    return doc["groups"]


def summarize_pairs(records):
    result = {"objects": len({r["object_id"] for r in records}), "cases": len(records)}
    for mode in ("single", "multi"):
        values = [r["comparison"][mode] for r in records]
        ranks = [v["top10"].index(r["gt"])+1 if r["gt"] in v["top10"] else 999 for r, v in zip(records, values)]
        times = sorted(v["elapsed_ms"] for v in values)
        result[mode] = {"n": len(records), **{f"{name}_k": sum(rank <= k for rank in ranks) for name, k in [("top1", 1), ("top3", 3), ("recall10", 10)]},
                        "latency_ms": {"p50": statistics.median(times) if times else None,
                                       "p95": statistics.quantiles(times, n=20, method="inclusive")[18] if len(times) > 1 else times[0] if times else None}}
    correct = lambda r, mode: bool(r["comparison"][mode]["top10"]) and r["comparison"][mode]["top10"][0] == r["gt"]
    result["wins"] = sum(not correct(r, "single") and correct(r, "multi") for r in records)
    result["regressions"] = sum(correct(r, "single") and not correct(r, "multi") for r in records)
    return result


def source_snapshot(root, groups, manifest=None):
    root = Path(root)
    paths = [root / "data" / name for name in ("parts.json", "labels.csv", "catalog.sqlite")]
    if manifest:
        paths.append(Path(manifest).resolve())
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        paths.extend(data_path(root, r["file"]) for r in csv.DictReader(f) if r["split"] == "catalog")
    for group in groups:
        for photo in group["photos"]:
            paths.append(data_path(root, photo["file"]))
            if photo.get("source"):
                paths.append(data_path(root, photo["source"]["file"]))
    return {str(p.resolve().relative_to(root.resolve())): sha256(p) for p in paths}


def validate_saved(doc, root=ROOT):
    if doc.get("schema") != 1 or doc.get("status") != "complete" or not doc.get("records") or not doc.get("sources_sha256"):
        raise ValueError("Incomplete paired experiment")
    for file, digest in doc["sources_sha256"].items():
        path = (Path(root) / file).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or sha256(path) != digest:
            raise ValueError("Paired experiment source changed")
    if doc.get("summary") != summarize_pairs(doc["records"]):
        raise ValueError("Paired experiment summary mismatch")
    if len(doc["records"]) != len(doc.get("groups", [])) or len({r["object_id"] for r in doc["records"]}) != len(doc["records"]):
        raise ValueError("Paired experiment coverage mismatch")
    for group, pair in zip(doc["groups"], doc["records"]):
        files = [p["file"] for p in group["photos"]]
        if pair["object_id"] != group["object_id"] or pair["gt"] != group["part_id"]:
            raise ValueError("Paired labels differ from manifest")
        if [p["file"] for p in pair["record"]["photos"]] != files or pair["baseline_record"]["photos"][0]["file"] != files[0]:
            raise ValueError("Paired photo order differs from manifest")
        for mode, key in (("single", "baseline_record"), ("multi", "record")):
            record = pair[key]
            ids = record["rankings"].get("gated", record["rankings"]["shape"])
            saved = pair["comparison"][mode]
            if saved["top10"] != ids[:10] or saved["top3"] != ids[:3] or saved["elapsed_ms"] != record["ms"]["total"]:
                raise ValueError("Paired result differs from measured record")
    return doc


def evaluate(groups, pipeline, root=ROOT, scope="exploratory_same_object", visual=False, manifest=None, force_visual=False):
    source = source_snapshot(root, groups, manifest)
    records = []
    namespace = "multi_experiment/" + str(time.time_ns())
    for i, group in enumerate(groups):
        paths = [data_path(root, p["file"]) for p in group["photos"]]
        output = compare_paths(pipeline, paths, visual, f"{namespace}/{i}", force_visual)
        for photo, info in zip(output["record"]["photos"], group["photos"]):
            photo["file"] = info["file"]
        output["baseline_record"]["photos"][0]["file"] = group["photos"][0]["file"]
        records.append({"object_id": group["object_id"], "gt": group["part_id"], **output})
        print(f"Paired {i+1}/{len(groups)}: {output['comparison']['single']['top3'][:1]} -> {output['comparison']['multi']['top3'][:1]}", flush=True)
    if source_snapshot(root, groups, manifest) != source:
        raise ValueError("Sources changed during paired experiment")
    doc = {"schema": 1, "status": "complete", "created_at": datetime.now(timezone.utc).isoformat(),
           "scope": scope, "visual_enabled": visual, "force_visual": force_visual, "groups": groups, "sources_sha256": source,
           "pipeline": pipeline.metadata, "records": records, "summary": summarize_pairs(records),
           "timing": "fresh extraction in both paths; retrieval initialization excluded; single first; requested VLM process/load included; no historical VLM cache"}
    return validate_saved(doc, root)


def report(root=ROOT):
    root = Path(root)
    directory = root / "results/multi_image"
    runs = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "report.json":
            continue
        doc = json.loads(path.read_text())
        if doc.get("schema") != 1:
            continue
        validate_saved(doc, root)
        runs.append({"file": path.name, "scope": doc["scope"], "visual_enabled": doc["visual_enabled"], "summary": doc["summary"]})
    result = {"runs": runs, "confirmed_objects": max((r["summary"]["objects"] for r in runs if r["scope"] == "confirmed_same_object"), default=0),
              "exploratory_objects": max((r["summary"]["objects"] for r in runs if r["scope"] == "exploratory_same_object"), default=0)}
    lines = ["# Single / multi-photo paired comparison", "", "Historical 44-photo experiments remain unchanged. Duplicate controls do not measure multi-angle benefit. Visually supported same-object groups are exploratory, not owner/expert-confirmed. Single runs first with loaded retrieval models shared; fresh query extraction in both paths, requested VLM process/loading included.", "",
             "| Run / scope | Groups / control sources | Top-1 single / multi | Top-3 | Recall@10 | p50 ms single / multi | gains / regressions |", "|---|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        s = run["summary"]; a, b = s["single"], s["multi"]
        lines.append(f"| {run['file']} / {run['scope']} | {s['objects']} | {a['top1_k']}/{a['n']} / {b['top1_k']}/{b['n']} | {a['top3_k']} / {b['top3_k']} | {a['recall10_k']} / {b['recall10_k']} | {a['latency_ms']['p50']:.1f} / {b['latency_ms']['p50']:.1f} | +{s['wins']} / -{s['regressions']} |")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (directory / "comparison.md").write_text("\n".join(lines) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["control", "run", "report"])
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--visual", action="store_true")
    parser.add_argument("--force-visual", action="store_true", help="Compare actual full VLM calls in both paths instead of the normal evidence gate")
    parser.add_argument("--output")
    parser.add_argument("--device")
    args = parser.parse_args()
    if args.command == "report":
        print(json.dumps(report(), indent=2)); return
    manifest = None
    if args.command == "run":
        manifest = Path(args.manifest or ROOT / "data/multi_image/manifest.json").resolve()
        groups = load_manifest(manifest)
        scope = json.loads(manifest.read_text())["scope"]
    else:
        with open(ROOT / "data/labels.csv", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["split"] == "query"]
        groups = [{"object_id": "control-" + str(i), "part_id": r["part_id"], "photos": [{"file": r["file"], "sha256": sha256(data_path(ROOT, r["file"]))}] * 3} for i, r in enumerate(rows)]
        scope = "duplicate_control"
    from .candidate_pipeline import make_candidate_pipeline
    setup = time.perf_counter()
    pipeline = make_candidate_pipeline(ROOT, requested_device=args.device)
    setup_ms = (time.perf_counter()-setup)*1000
    if args.force_visual and not args.visual:
        parser.error("--force-visual requires --visual")
    doc = evaluate(groups, pipeline, scope=scope, visual=args.visual, manifest=manifest, force_visual=args.force_visual)
    doc["retrieval_setup_ms"] = setup_ms
    path = Path(args.output or ROOT / "results/multi_image" / ("duplicate_control.json" if args.command == "control" else "paired_visual.json" if args.visual else "paired_retrieval.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    report()


if __name__ == "__main__":
    main()
