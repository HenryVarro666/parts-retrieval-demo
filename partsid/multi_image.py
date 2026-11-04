"""Same-object photo fusion; query labels and filenames never enter inference."""
import copy
import hashlib
import json
import math
import random
import time
import uuid
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

from .candidate_pipeline import can_accept_sql, prepare_visual, run_visual_requests, sha256
from .rerank import build_prompt

POLICY = "multi-photo-rrf60-v1"


def image_signature(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        thumb = list(image.convert("L").resize((32, 32)).tobytes())
        small = list(image.convert("L").resize((9, 8)).tobytes())
        dhash = sum((small[y*9+x] > small[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))
        return {"pixel_sha256": pixel_hash, "width": image.width, "height": image.height,
                "thumbnail": thumb, "dhash": dhash}


def correlation_groups(signatures):
    """Conservative near-copy grouping; fixed thresholds, no development-set fitting."""
    groups, representatives = [], []
    for item in signatures:
        found = None
        for index in representatives:
            ref = signatures[index]
            ratio = (item["width"] / item["height"]) / (ref["width"] / ref["height"])
            rmse = math.sqrt(sum((a-b)**2 for a, b in zip(item["thumbnail"], ref["thumbnail"])) / 1024) / 255
            if item["pixel_sha256"] == ref["pixel_sha256"] or (0.98 <= ratio <= 1.02 and
                    (item["dhash"] ^ ref["dhash"]).bit_count() <= 2 and rmse <= 0.035):
                found = groups[index]
                break
        if found is None:
            found = len(representatives)
            representatives.append(len(groups))
        groups.append(found)
    return groups


def fuse_records(records, groups):
    if not records or len(records) != len(groups):
        raise ValueError("Every photo needs a record and correlation group")
    weights = [1 / Counter(groups)[group] for group in groups]
    universe = list(dict.fromkeys(pid for r in records for pid in r["retrieval"]["candidate_ids"]))
    support = {pid: {"part_id": pid, "score": 0.0, "sql_photos": [], "appearance_photos": [],
                     "shape_photos": [], "strong_photos": [], "strong_groups": []} for pid in universe}
    text_scores, image_scores, shape_scores = dict.fromkeys(universe, 0.0), dict.fromkeys(universe, 0.0), dict.fromkeys(universe, 0.0)
    receipts, keywords, conflicts = {}, [], []
    for index, (record, group, weight) in enumerate(zip(records, groups, weights)):
        for keyword in record["retrieval"].get("keywords", []):
            keywords.append({**keyword, "photo_index": index})
        conflicts.extend({"photo_index": index, "detail": c} for c in record.get("evidence", {}).get("conflicts", []))
        for candidate in record["retrieval"].get("candidates", []):
            pid = candidate["part_id"]
            entry = receipts.setdefault(pid, {**copy.deepcopy(candidate), "matches": []})
            entry["matches"].extend({**m, "photo_index": index} for m in candidate.get("matches", []))
        for channel, target, field in [("sql", text_scores, "sql_photos"), ("image", image_scores, "appearance_photos")]:
            for rank, pid in enumerate(dict.fromkeys(record["rankings"].get(channel, [])), 1):
                if pid in support:
                    target[pid] += weight / (60 + rank)
                    support[pid][field].append(index)
        known = [pid for pid, score in record.get("shape", {}).get("reference_scores", {}).items()
                 if score is not None and math.isfinite(score) and pid in support]
        known.sort(key=lambda pid: (-record["shape"]["reference_scores"][pid], pid))
        for rank, pid in enumerate(known, 1):
            shape_scores[pid] += weight / (60 + rank)
            support[pid]["shape_photos"].append(index)
        for pid in record["retrieval"].get("strong_ids", []):
            if pid in support:
                support[pid]["strong_photos"].append(index)
                if group not in support[pid]["strong_groups"]:
                    support[pid]["strong_groups"].append(group)
    for pid, item in support.items():
        item["score"] = text_scores[pid] + image_scores[pid] + shape_scores[pid]
    strong = [pid for pid in universe if support[pid]["strong_groups"]]
    strong.sort(key=lambda pid: (-len(support[pid]["strong_groups"]), -support[pid]["score"], pid))
    if len(strong) > 1:
        conflicts.append({"kind": "cross_photo_strong_conflict", "part_ids": strong})
    hybrid = strong + sorted((pid for pid in universe if pid not in strong), key=lambda p: (-text_scores[p]-image_scores[p], p))
    hybrid = hybrid[:10]
    ranked = [pid for pid in strong if pid in hybrid] + sorted((pid for pid in hybrid if pid not in strong), key=lambda p: (-support[p]["score"], p))
    result = copy.deepcopy(records[0])
    if len(records) > 1 and not all(r == records[0] for r in records):
        result["rankings"] = {"sql": sorted(receipts, key=lambda p: (p not in strong, -text_scores.get(p, 0), p)),
                              "image": sorted(universe, key=lambda p: (-image_scores[p], p)),
                              "hybrid": hybrid, "shape": ranked, "fused": ranked}
        means = {}
        for pid in hybrid:
            values = [(r["shape"]["reference_scores"].get(pid), w) for r, w in zip(records, weights)
                      if r.get("shape", {}).get("reference_scores", {}).get(pid) is not None]
            values = [(v, w) for v, w in values if math.isfinite(v)]
            means[pid] = sum(v*w for v, w in values) / sum(w for _, w in values) if values else None
        result["shape"] = {"query": {"available": False, "features": {}, "quality_notes": ["multi_photo_per_image_geometry"]},
                           "reference_scores": means, "ranked_ids": ranked}
    else:
        hybrid = list(result["retrieval"]["candidate_ids"])
    origins = {pid: list(dict.fromkeys(origin for r in records for p in r["retrieval"].get("pool", [])
                                     if p["part_id"] == pid for origin in p.get("origins", []))) for pid in hybrid}
    result["retrieval"].update(candidate_ids=hybrid, strong_ids=strong,
        candidates=[receipts[p] for p in result["rankings"]["sql"] if p in receipts], keywords=keywords,
        sql_candidate_ids=list(result["rankings"]["sql"]), fallback_used=any("appearance" in v for v in origins.values()),
        pool=[{"part_id": pid, "origins": origins[pid]} for pid in hybrid])
    result["evidence"]["conflicts"] = conflicts
    result["fusion"] = {"policy": POLICY, "photo_count": len(records), "independent_groups": len(set(groups)),
                        "groups": groups, "weights": weights, "support": support}
    return result


def can_accept_group(record):
    fusion = record.get("fusion", {})
    if fusion.get("photo_count", 1) == 1:
        return can_accept_sql(record)
    strong = record["retrieval"].get("strong_ids", [])
    return (len(strong) == 1 and len(fusion["support"][strong[0]]["strong_groups"]) >= 2
            and record["rankings"]["shape"][0] == strong[0] and not record["evidence"].get("conflicts"))


def apply_group_visual(record, decision):
    result = copy.deepcopy(record)
    selected = decision.get("selected_id")
    valid = decision.get("abstained") is False and selected in result["retrieval"]["candidate_ids"]
    decision = {**decision, "selected_id": selected if valid else None, "abstained": not valid}
    base = result["rankings"]["shape"]
    ranked = [selected] + [p for p in base if p != selected] if valid else list(base)
    result["rankings"].update(reranked=ranked, gated=ranked, fused=ranked)
    result["vlm"] = decision
    result["decision"] = {"used_vlm": True, "actual_vlm_executed": True,
                          "reason_code": "joint_visual" if valid else "joint_abstention"}
    return result


def prepare_group_visual(pipeline, record, paths, namespace):
    from .experiments import contact_sheet
    unique = [p["index"] for p in record["photos"] if p["duplicate_of"] is None]
    if len(unique) == 1:
        return prepare_visual(pipeline.root, record, paths[unique[0]], pipeline.parts, pipeline.reference_paths, namespace)
    hashes = [sha256(paths[i]) for i in unique]
    ids = list(record["retrieval"]["candidate_ids"])
    shuffled = list(ids)
    random.Random("".join(hashes)).shuffle(shuffled)
    candidates = [pipeline.parts[pid] for pid in shuffled]
    count = len(unique)
    prompt = build_prompt(candidates, query_count=count)
    geometry = [{"image": n+1, "correlation_group": record["photos"][i]["group"],
                 "shape": {k: record["photos"][i]["record"]["shape"]["query"].get(k) for k in ("available", "features")}}
                for n, i in enumerate(unique)]
    prompt += ("\nThese are asserted to show the same physical object. If visible models conflict, abstain. "
               "Near-copy correlation groups do not provide independent confirmation. Describe visible markings by "
               "image number in observed_text. Geometry is heuristic, not calibrated dimensions or pin counts:\n" +
               json.dumps(geometry, ensure_ascii=False))
    key = hashlib.sha256(json.dumps([hashes, ids, prompt]).encode()).hexdigest()[:20]
    directory = Path(pipeline.root) / "data/cache" / namespace
    directory.mkdir(parents=True, exist_ok=True)
    sheet = directory / f"{key}.jpg"
    contact_sheet(candidates, {pid: str(p) for pid, p in pipeline.reference_paths.items()}, sheet)
    return {"key": key, "images": [str(Path(paths[i]).resolve()) for i in unique] + [str(sheet.resolve())],
            "images_sha256": hashes + [sha256(sheet)], "input_sha256": hashlib.sha256("".join(hashes).encode()).hexdigest(),
            "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "candidate_ids": ids}


def run_group(pipeline, paths, verify_visual=False, namespace=None, force_visual=False):
    if not 1 <= len(paths) <= 3:
        raise ValueError("Use one to three photos")
    started = time.perf_counter()
    signatures = [image_signature(p) for p in paths]
    groups = correlation_groups(signatures)
    by_pixels, records, photos = {}, [], []
    for index, (path, sig, group) in enumerate(zip(paths, signatures, groups)):
        old = by_pixels.get(sig["pixel_sha256"])
        record = records[old] if old is not None else pipeline.run(path)
        by_pixels.setdefault(sig["pixel_sha256"], index)
        records.append(record)
        photos.append({"index": index, "group": group, "duplicate_of": old,
                       "pixel_sha256": sig["pixel_sha256"], "width": sig["width"], "height": sig["height"],
                       "record": copy.deepcopy(record)})
    fusion_start = time.perf_counter()
    result = fuse_records(records, groups)
    result["photos"] = photos
    result["ms"] = {stage: sum(r.get("ms", {}).get(stage, 0) for i, r in enumerate(records) if photos[i]["duplicate_of"] is None)
                    for stage in ("ocr", "sqlite", "image", "shape")}
    result["ms"]["fusion"] = (time.perf_counter()-fusion_start)*1000
    if verify_visual:
        if can_accept_group(result) and not force_visual:
            result["rankings"]["gated"] = list(result["rankings"]["shape"])
            result["decision"] = {"used_vlm": False, "actual_vlm_executed": False, "reason_code": "single_strong" if len(paths) == 1 else "multi_consensus"}
        else:
            visual_start = time.perf_counter()
            namespace = namespace or "multi_live/" + uuid.uuid4().hex
            request = prepare_group_visual(pipeline, result, paths, namespace)
            decisions, metadata = run_visual_requests(pipeline.root, [request], namespace)
            result = apply_group_visual(result, decisions[0])
            result["visual_runtime"] = metadata
            result["ms"]["vlm"] = (time.perf_counter()-visual_start)*1000
    result["ms"]["total"] = (time.perf_counter()-started)*1000
    return result


def compare_paths(pipeline, paths, verify_visual=False, namespace=None, force_visual=False):
    started = time.perf_counter()
    namespace = namespace or "multi_live/" + uuid.uuid4().hex
    single = run_group(pipeline, paths[:1], verify_visual, namespace + "/single", force_visual)
    multi = run_group(pipeline, paths, verify_visual, namespace + "/multi", force_visual) if len(paths) > 1 else single
    def summary(record):
        ids = record["rankings"].get("gated", record["rankings"]["shape"])
        return {"top3": ids[:3], "top10": ids[:10], "elapsed_ms": record["ms"]["total"],
                "vlm_executed": record.get("decision", {}).get("actual_vlm_executed", False),
                "vlm_cache_reused": record.get("vlm", {}).get("cache_reused", False)}
    return {"record": multi, "baseline_record": single,
            "comparison": {"single": summary(single), "multi": summary(multi), "photo_count": len(paths),
                           "independent_groups": multi["fusion"]["independent_groups"],
                           "request_elapsed_ms": (time.perf_counter()-started)*1000,
                           "timing_scope": "two independent query runs; loaded retrieval models shared; single first; VLM process/load included; no cross-run query reuse"}}
