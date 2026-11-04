"""Paired same-object evaluation, kept separate from the historical 44 photos."""
import argparse
import csv
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

from .candidate_pipeline import ROOT, sha256
from .multi_image import compare_paths, image_signature, run_group


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
    if doc.get("selection_file"):
        selection_path = (Path(root) / doc["selection_file"]).resolve()
        if (not selection_path.is_relative_to((Path(root) / "data").resolve())
                or sha256(selection_path) != doc.get("selection_sha256")):
            raise ValueError("Frozen selection changed")
        selection = json.loads(selection_path.read_text())
        selected = [{**g, "photos": [{"source": p["source"]} for p in g["photos"]]} for g in doc["groups"]]
        if selected != selection["groups"] or doc.get("cohort") != selection.get("cohort"):
            raise ValueError("Manifest differs from frozen selection")
    parts_path = Path(root) / "data/parts.json"
    part_ids = {p["id"] for p in json.loads(parts_path.read_text())} if parts_path.exists() else None
    with open(Path(root) / "data/labels.csv", encoding="utf-8") as f:
        catalog_rows = [r for r in csv.DictReader(f) if r["split"] == "catalog"]
    catalog_paths = [data_path(root, r["file"]) for r in catalog_rows]
    catalog_pageids = {str(r["pageid"]) for r in catalog_rows if r.get("pageid")}
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
        pixels, captures = [], []
        capture_metadata = {key: [] for key in ("capture_id", "original_document_id", "pageid")}
        for photo in photos:
            file = data_path(root, photo.get("file"))
            if photo.get("sha256") != sha256(file):
                raise ValueError("Stale photo hash")
            sig = image_signature(file)
            if sig["width"] * sig["height"] > 16_000_000 or file.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Photo exceeds upload budget")
            pixels.append(sig["pixel_sha256"])
            source = photo.get("source")
            captures.append(sig["pixel_sha256"])
            if source:
                if str(source.get("pageid")) in catalog_pageids:
                    raise ValueError("Paired source capture overlaps catalog")
                for key, values in capture_metadata.items():
                    if source.get(key):
                        values.append(str(source[key]))
                original = data_path(root, source.get("file"))
                if source.get("sha256") != sha256(original):
                    raise ValueError("Stale original hash")
                if original in catalog_paths:
                    raise ValueError("Paired source overlaps catalog")
                captures[-1] = image_signature(original)["pixel_sha256"]
                if captures[-1] in catalog_pixels:
                    raise ValueError("Paired source pixels overlap catalog")
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
        if len(set(captures)) != 3:
            raise ValueError("Three independent source captures are required; crops of one capture are not separate photos")
        if any(len(values) != len(set(values)) for values in capture_metadata.values()):
            raise ValueError("Duplicate canonical capture metadata; resized/edited copies are one capture")
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
    if records and all("single_photo_records" in r for r in records):
        singles = [r for pair in records for r in pair["single_photo_records"]]
        labels = [pair["gt"] for pair in records for _ in pair["single_photo_records"]]
        ranks = []
        for record, label in zip(singles, labels):
            ids = record["rankings"].get("gated", record["rankings"]["shape"])[:10]
            ranks.append(ids.index(label)+1 if label in ids else 999)
        times = [r["ms"]["total"] for r in singles]
        result["all_single"] = {"n": len(singles), "objects": result["objects"],
            **{f"{name}_k": sum(rank <= k for rank in ranks) for name, k in [("top1", 1), ("top3", 3), ("recall10", 10)]},
            "latency_ms": {"p50": statistics.median(times), "p95": statistics.quantiles(times, n=20, method="inclusive")[18]},
            "vlm_calls": sum(r.get("decision", {}).get("actual_vlm_executed", False) for r in singles)}
    return result


def summarize_strata(records, groups):
    result = {}
    for field in ("cohort_kind", "capture_kind", "quality_stratum"):
        values = sorted({g[field] for g in groups if field in g})
        if values:
            result[field] = {v: summarize_pairs([r for r, g in zip(records, groups) if g.get(field) == v]) for v in values}
    return result


def source_dependencies(root, groups, manifest=None):
    """Logical paths matter: retargeting a symlink must invalidate web replay."""
    root = Path(root).resolve()
    paths = [root / "data" / name for name in ("parts.json", "labels.csv", "catalog.sqlite")]
    if manifest:
        paths.append(Path(manifest).resolve())
        selection = json.loads(Path(manifest).read_text()).get("selection_file")
        if selection:
            paths.append(root / selection)
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        paths.extend(root / "data" / r["file"] for r in csv.DictReader(f) if r["split"] == "catalog")
    for group in groups:
        for photo in group["photos"]:
            data_path(root, photo["file"])
            paths.append(root / "data" / photo["file"])
            if photo.get("source"):
                data_path(root, photo["source"]["file"])
                paths.append(root / "data" / photo["source"]["file"])
    return paths


def source_snapshot(root, groups, manifest=None):
    paths = source_dependencies(root, groups, manifest)
    root = Path(root)
    return {str(p.resolve().relative_to(root.resolve())): sha256(p) for p in paths}


def _write_atomic(path, text):
    """Readers (the web server) never observe a half-written results file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def replay_fingerprint(doc, root):
    manifest = Path(root) / doc["manifest_file"] if doc.get("manifest_file") else None
    result = []
    for path in source_dependencies(root, doc["groups"], manifest):
        resolved = path.resolve()
        if not resolved.is_relative_to(Path(root).resolve()):
            raise ValueError("Replay dependency escapes root")
        result.append((str(path), str(resolved), sha256(resolved)))
    return tuple(result)


def validate_saved(doc, root=ROOT):
    if doc.get("schema") != 1 or doc.get("status") != "complete" or not doc.get("records") or not doc.get("sources_sha256"):
        raise ValueError("Incomplete paired experiment")
    manifest = Path(root) / doc["manifest_file"] if doc.get("manifest_file") else None
    if source_snapshot(root, doc.get("groups", []), manifest) != doc["sources_sha256"]:
        raise ValueError("Paired source coverage or bytes changed")
    for file, digest in doc["sources_sha256"].items():
        path = (Path(root) / file).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or sha256(path) != digest:
            raise ValueError("Paired experiment source changed")
    scope = doc.get("scope")
    if scope == "duplicate_control":
        for group in doc.get("groups", []):
            pixels = [image_signature(data_path(root, p["file"]))["pixel_sha256"] for p in group["photos"]]
            if len(pixels) != 3 or len(set(pixels)) != 1:
                raise ValueError("Duplicate controls require one capture repeated three times")
    elif scope in ("exploratory_same_object", "confirmed_same_object"):
        manifest = doc.get("manifest_file")
        if not isinstance(manifest, str) or manifest not in doc["sources_sha256"]:
            raise ValueError("Paired experiment requires its hashed source manifest")
        path = (Path(root) / manifest).resolve()
        source = json.loads(path.read_text())
        if scope != source.get("scope") or doc.get("groups") != load_manifest(path, root):
            raise ValueError("Paired scope/groups differ from the source manifest")
    else:
        raise ValueError("Unknown paired experiment scope")
    if doc.get("summary") != summarize_pairs(doc["records"]):
        raise ValueError("Paired experiment summary mismatch")
    if "strata_summary" in doc and doc["strata_summary"] != summarize_strata(doc["records"], doc["groups"]):
        raise ValueError("Paired experiment strata mismatch")
    if len(doc["records"]) != len(doc.get("groups", [])) or len({r["object_id"] for r in doc["records"]}) != len(doc["records"]):
        raise ValueError("Paired experiment coverage mismatch")
    for group, pair in zip(doc["groups"], doc["records"]):
        files = [p["file"] for p in group["photos"]]
        if pair["object_id"] != group["object_id"] or pair["gt"] != group["part_id"]:
            raise ValueError("Paired labels differ from manifest")
        if [p["file"] for p in pair["record"]["photos"]] != files or pair["baseline_record"]["photos"][0]["file"] != files[0]:
            raise ValueError("Paired photo order differs from manifest")
        singles = pair.get("single_photo_records")
        if doc.get("all_single_views") and (not isinstance(singles, list) or len(singles) != 3):
            raise ValueError("Missing standalone single-photo measurements")
        if singles:
            if (len(singles) != 3 or singles[0] != pair["baseline_record"]
                    or any(len(r.get("photos", [])) != 1 or r["photos"][0]["file"] != file for r, file in zip(singles, files))):
                raise ValueError("Standalone single-photo order differs from manifest")
        for mode, key in (("single", "baseline_record"), ("multi", "record")):
            record = pair[key]
            ids = record["rankings"].get("gated", record["rankings"]["shape"])
            saved = pair["comparison"][mode]
            if saved["top10"] != ids[:10] or saved["top3"] != ids[:3] or saved["elapsed_ms"] != record["ms"]["total"]:
                raise ValueError("Paired result differs from measured record")
    return doc


def evaluate(groups, pipeline, root=ROOT, scope="exploratory_same_object", visual=False, manifest=None, force_visual=False, all_single_views=False):
    source = source_snapshot(root, groups, manifest)
    records = []
    namespace = "multi_experiment/" + str(time.time_ns())
    for i, group in enumerate(groups):
        paths = [data_path(root, p["file"]) for p in group["photos"]]
        output = compare_paths(pipeline, paths, visual, f"{namespace}/{i}", force_visual)
        for photo, info in zip(output["record"]["photos"], group["photos"]):
            photo["file"] = info["file"]
            if info.get("source"):
                photo["source"] = info["source"]
        output["baseline_record"]["photos"][0]["file"] = group["photos"][0]["file"]
        if all_single_views:
            singles = [output["baseline_record"]]
            for j, (path, info) in enumerate(zip(paths[1:], group["photos"][1:]), 1):
                record = run_group(pipeline, [path], visual, f"{namespace}/{i}/view-{j}", force_visual)
                record["photos"][0]["file"] = info["file"]
                singles.append(record)
            output["single_photo_records"] = singles
        records.append({"object_id": group["object_id"], "gt": group["part_id"], **output})
        print(f"Paired {i+1}/{len(groups)}: {output['comparison']['single']['top3'][:1]} -> {output['comparison']['multi']['top3'][:1]}", flush=True)
    if source_snapshot(root, groups, manifest) != source:
        raise ValueError("Sources changed during paired experiment")
    doc = {"schema": 1, "status": "complete", "created_at": datetime.now(UTC).isoformat(),
           "scope": scope, "visual_enabled": visual, "force_visual": force_visual, "groups": groups, "sources_sha256": source,
           "manifest_file": str(Path(manifest).resolve().relative_to(Path(root).resolve())) if manifest else None,
           "pipeline": pipeline.metadata, "records": records, "summary": summarize_pairs(records),
           "timing": "fresh extraction in both paths; retrieval initialization excluded; single first; requested VLM process/load included; no historical VLM cache"}
    doc["execution"] = {"platform": platform.platform(), "machine": platform.machine(),
        "code_sha256": {f"partsid/{p.name}": sha256(p) for p in sorted((Path(root) / "partsid").glob("*.py"))}}
    if all_single_views:
        doc.update(all_single_views=True, strata_summary=summarize_strata(records, groups))
        doc["timing"] += "; then views 2 and 3 measured standalone with fresh extraction; 3N single views are clustered in N objects"
    if manifest:
        doc["cohort"] = json.loads(Path(manifest).read_text()).get("cohort")
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
        runs.append({"file": path.name, "scope": doc["scope"], "cohort": doc.get("cohort"), "visual_enabled": doc["visual_enabled"], "force_visual": doc.get("force_visual", False), "summary": doc["summary"],
                     **({"strata_summary": doc["strata_summary"]} if "strata_summary" in doc else {})})
    result = {"runs": runs, "confirmed_objects": max((r["summary"]["objects"] for r in runs if r["scope"] == "confirmed_same_object"), default=0),
              "exploratory_objects": max((r["summary"]["objects"] for r in runs if r["scope"] == "exploratory_same_object"), default=0)}
    lines = ["# Single / multi-photo paired comparison", "", "Historical 44-photo experiments remain unchanged. Duplicate controls do not measure multi-angle benefit. Visually supported same-object groups are exploratory, not owner/expert-confirmed. Single runs first with loaded retrieval models shared; fresh query extraction in both paths, requested VLM process/loading included.", "",
             "| Run / scope | Groups / control sources | Top-1 single / multi | Top-3 | Recall@10 | p50 ms single / multi | gains / regressions |", "|---|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        s = run["summary"]; a, b = s["single"], s["multi"]
        lines.append(f"| {run['file']} / {run['scope']} | {s['objects']} | {a['top1_k']}/{a['n']} / {b['top1_k']}/{b['n']} | {a['top3_k']} / {b['top3_k']} | {a['recall10_k']} / {b['recall10_k']} | {a['latency_ms']['p50']:.1f} / {b['latency_ms']['p50']:.1f} | +{s['wins']} / -{s['regressions']} |")
    for path in sorted(directory.glob("public_*.json")):
        doc = json.loads(path.read_text()); s = doc["summary"]
        if not doc.get("cohort") or not doc.get("all_single_views"):
            continue
        lines.extend(["", f"## {path.name}: frozen public triplets", "",
            "First predetermined view vs all three; auxiliary all-single results measure every view independently, not 3N independent objects. Still/video, new/anchor and unreadable-marking quality strata (including glare) are separate in report.json.", "",
            f"All single views: {s['all_single']['top1_k']}/{s['all_single']['n']} Top-1, {s['all_single']['objects']} object clusters; p50/p95 {s['all_single']['latency_ms']['p50']:.1f}/{s['all_single']['latency_ms']['p95']:.1f} ms.",
            f"Paired p95 single/multi: {s['single']['latency_ms']['p95']:.1f}/{s['multi']['latency_ms']['p95']:.1f} ms.", "",
            "| Object / label / capture | Standalone views 1 / 2 / 3 | Three-view Top-1 | Paired time ms single / multi |", "|---|---|---|---:|"])
        for group, pair in zip(doc["groups"], doc["records"]):
            ids = [(r["rankings"].get("gated", r["rankings"]["shape"]) or ["—"])[0] for r in pair["single_photo_records"]]
            lines.append(f"| {pair['object_id']} / {pair['gt']} / {group['capture_kind']} | {' / '.join(ids)} | {pair['comparison']['multi']['top10'][0]} | {pair['comparison']['single']['elapsed_ms']:.1f} / {pair['comparison']['multi']['elapsed_ms']:.1f} |")
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomic(directory / "report.json", json.dumps(result, ensure_ascii=False, indent=2))
    _write_atomic(directory / "comparison.md", "\n".join(lines) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["control", "run", "report"])
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--visual", action="store_true")
    parser.add_argument("--force-visual", action="store_true", help="Compare actual full VLM calls in both paths instead of the normal evidence gate")
    parser.add_argument("--all-single-views", action="store_true", help="Additionally measure views 2 and 3 standalone; view 1 is the paired baseline")
    parser.add_argument("--output")
    parser.add_argument("--device")
    args = parser.parse_args()
    if args.force_visual and not args.visual:
        parser.error("--force-visual requires --visual")
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
    doc = evaluate(groups, pipeline, scope=scope, visual=args.visual, manifest=manifest, force_visual=args.force_visual, all_single_views=args.all_single_views)
    doc["retrieval_setup_ms"] = setup_ms
    path = Path(args.output or ROOT / "results/multi_image" / ("duplicate_control.json" if args.command == "control" else "paired_visual.json" if args.visual else "paired_retrieval.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, json.dumps(doc, ensure_ascii=False, indent=2))
    report()


if __name__ == "__main__":
    main()
