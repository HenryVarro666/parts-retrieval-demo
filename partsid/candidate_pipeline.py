"""OCR -> SQLite candidates -> soft shape evidence -> constrained visual check."""
import copy
import csv
import hashlib
import json
import math
import random
import subprocess
import time
from pathlib import Path

from .fusion import rrf
from .rerank import build_prompt, validate_response

ROOT = Path(__file__).resolve().parent.parent
MODEL = "mlx-community/Qwen3-VL-4B-Instruct-4bit"
REVISION = "2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b"
VISUAL_TIMEOUT_S = 600  # Worker start plus model load.
VISUAL_TIMEOUT_PER_REQUEST_S = 120


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def merge_candidates(sql_candidates, image_ids, strong_ids, k=10):
    """Explicit text top5/appearance top5 union, strong aliases protected."""
    if k < 1:
        raise ValueError("Candidate limit must be positive")
    sql_ids = list(dict.fromkeys(c["part_id"] for c in sql_candidates))
    images = list(dict.fromkeys(image_ids))
    pool, by_id = [], {}
    def add(ids, origin):
        for pid in ids:
            if pid in by_id:
                if origin not in by_id[pid]["origins"]:
                    by_id[pid]["origins"].append(origin)
            elif len(pool) < k:
                item = {"part_id": pid, "origins": [origin],
                        "sql_rank": sql_ids.index(pid) + 1 if pid in sql_ids else None,
                        "appearance_rank": images.index(pid) + 1 if pid in images else None}
                by_id[pid] = item
                pool.append(item)
    add([pid for pid in sql_ids if pid in strong_ids], "sqlite")
    add(sql_ids[:5], "sqlite")
    add(images[:5], "appearance")
    add(sql_ids[5:], "sqlite")
    add(images[5:], "appearance")
    return pool


def shape_rerank(ids, strong_ids, scores):
    strong = [pid for pid in ids if pid in strong_ids]
    known = [pid for pid in ids if scores.get(pid) is not None and math.isfinite(scores[pid])]
    known.sort(key=lambda pid: (-scores[pid], pid))
    ranked = [pid for pid, _ in rrf({"retrieval": ids, "shape": known})]
    return strong + [pid for pid in ranked if pid not in strong]


def can_accept_sql(record):
    strong = record["retrieval"].get("strong_ids", [])
    return (len(strong) == 1 and strong[0] == record["rankings"]["shape"][0]
            and not record.get("evidence", {}).get("conflicts"))


def apply_visual(record, decision):
    result = copy.deepcopy(record)
    pool = result["retrieval"]["candidate_ids"]
    chosen = decision.get("selected_id")
    valid = decision.get("abstained") is False and isinstance(chosen, str) and chosen in pool
    decision = {**decision, "selected_id": chosen if valid else None, "abstained": not valid}
    base = result["rankings"]["shape"]
    result["rankings"]["reranked"] = [chosen] + [p for p in base if p != chosen] if valid else list(base)
    accepted = can_accept_sql(result)
    result["rankings"]["gated"] = list(base) if accepted else result["rankings"]["reranked"]
    result["rankings"]["fused"] = result["rankings"]["gated"]
    result["vlm"] = decision
    result["decision"] = {"used_vlm": not accepted, "actual_vlm_executed": True,
                          "reason": "唯一明确 SQL 型号且无视图冲突，保留检索结果" if accepted
                          else "视觉模型弃权，保留形状重排结果" if not valid else "使用新候选集的视觉核验结果"}
    return result


def candidate_prompt(candidates, query_shape, scores):
    # Public catalog whitelist is enforced again by build_prompt.
    visible = {"available": bool(query_shape.get("available")), "features": query_shape.get("features", {})}
    allowed = {p["id"] for p in candidates}
    extras = {"query_foreground_shape": visible,
              "candidate_shape_similarities": {pid: score for pid, score in scores.items() if pid in allowed}}
    return (build_prompt(candidates) + "\nAdditional measured foreground geometry (heuristic, uncalibrated, "
            "not a package identity or pin count; unknown means no evidence). Do not override clearly "
            "visible markings merely because of a shape score:\n" + json.dumps(extras, ensure_ascii=False))


class CandidatePipeline:
    def __init__(self, root, parts, references, db, ocr, image_encoder, device):
        import numpy as np

        from .images import load_rgb
        from .shape import describe_shape
        self.root, self.parts, self.references = Path(root), {p["id"]: p for p in parts}, references
        self.db, self.ocr, self.image_encoder, self.device = db, ocr, image_encoder, device
        self.reference_paths = {r["part_id"]: self.root / "data" / r["file"] for r in references}
        self.reference_ids = list(self.reference_paths)
        self.reference_vectors = np.concatenate([image_encoder.encode([load_rgb(self.reference_paths[pid]) for pid in self.reference_ids[i:i+16]])
                                                for i in range(0, len(self.reference_ids), 16)])
        self.reference_shapes = {pid: describe_shape(path) for pid, path in self.reference_paths.items()}

    @property
    def metadata(self):
        return {"ocr": self.ocr.metadata, "sqlite": self.db.metadata,
                "image_model": self.image_encoder.model_id, "image_revision": self.image_encoder.revision,
                "reference_image_sha256": {pid: sha256(path) for pid, path in self.reference_paths.items()},
                "pool_policy": "strong SQL first; SQL top5 + appearance top5; fill SQL then appearance to10",
                "shape_policy": "preserve exact/folded aliases; otherwise k60 RRF of retrieval and known shape rank"}

    def run(self, path):
        from . import identifier
        from .device import synchronize
        from .images import load_rgb
        from .shape import compare_shapes, describe_shape
        start = time.perf_counter()
        text = self.ocr.read(path)
        evidence = copy.deepcopy(self.ocr.last_result)
        t = time.perf_counter()
        ms = {"ocr": (t-start)*1000}
        view = next((v for v in evidence["views"] if v["id"] == evidence["selected_view"]), None)
        threshold = self.ocr.metadata.get("text_min_confidence", 0.2)
        boxes = [{**box, "view_id": view["id"]} for box in view["boxes"] if box["confidence"] >= threshold] if view else None
        retrieval = self.db.search(text, limit=10, boxes=boxes)
        ms["sqlite"] = (time.perf_counter()-t)*1000
        sql_total = (time.perf_counter()-start)*1000
        t = time.perf_counter()
        query = self.image_encoder.encode([load_rgb(path)])[0]
        sims = self.reference_vectors @ query
        appearance = sorted(zip(self.reference_ids, map(float, sims)), key=lambda item: (-item[1], item[0]))
        synchronize(self.device)
        ms["image"] = (time.perf_counter()-t)*1000
        t = time.perf_counter()
        pool = merge_candidates(retrieval["candidates"], [pid for pid, _ in appearance], retrieval["strong_ids"])
        ids = [p["part_id"] for p in pool]
        hybrid_total = (time.perf_counter()-start)*1000
        shape = describe_shape(path)
        scores = {pid: compare_shapes(shape, self.reference_shapes[pid]) for pid in ids}
        shape_ids = shape_rerank(ids, retrieval["strong_ids"], scores)
        ms["shape"] = (time.perf_counter()-t)*1000
        ms["total"] = (time.perf_counter()-start)*1000
        retrieval.update(pool=pool, sql_candidate_ids=[c["part_id"] for c in retrieval["candidates"]],
                         candidate_ids=ids, fallback_used=any("appearance" in p["origins"] for p in pool))
        return {"ocr_text": text, "evidence": evidence, "retrieval": retrieval,
                "shape": {"query": shape, "reference_scores": scores, "ranked_ids": shape_ids},
                "id_hits": identifier.rank(text, list(self.parts.values())),
                "rankings": {"sql": retrieval["sql_candidate_ids"], "hybrid": ids, "shape": shape_ids,
                             "image": [pid for pid, _ in appearance], "fused": shape_ids},
                "image_sims": dict(appearance), "ms": ms,
                "stage_totals": {"sql": sql_total, "hybrid": hybrid_total, "shape": ms["total"]}}


def make_candidate_pipeline(root=ROOT, engine="rapidocr", multiview=True, requested_device=None):
    from .device import pick_device
    from .embed import ImageEncoder
    from .evidence_ocr import EvidenceOCR
    from .sqlite_catalog import SQLiteCatalog, build_catalog
    root = Path(root)
    parts = json.loads((root / "data/parts.json").read_text())
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        references = [{"part_id": r["part_id"], "file": r["file"]} for r in csv.DictReader(f) if r["split"] == "catalog"]
    db_path = root / "data/catalog.sqlite"
    if not db_path.exists():
        build_catalog(parts, db_path, references)
    db = SQLiteCatalog(db_path)
    expected = hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if db.metadata["catalog_sha256"] != expected:
        raise ValueError("SQLite catalog is stale; run python -m partsid.candidate_experiments build")
    reference_manifest = sorted({(r["part_id"], r["file"]) for r in references})
    expected_refs = hashlib.sha256(json.dumps(reference_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if db.metadata["references_sha256"] != expected_refs:
        raise ValueError("SQLite reference manifest is stale; rebuild the catalog")
    device = pick_device(requested_device)
    return CandidatePipeline(root, parts, references, db, EvidenceOCR(engine, device, parts, multiview), ImageEncoder(device), device)


def prepare_visual(root, record, path, parts, reference_paths, namespace):
    from .experiments import contact_sheet
    ids = list(record["retrieval"]["candidate_ids"])
    shuffled = list(ids)
    random.Random(sha256(path)).shuffle(shuffled)
    candidates = [parts[pid] for pid in shuffled]
    prompt = candidate_prompt(candidates, record["shape"]["query"], record["shape"]["reference_scores"])
    key = hashlib.sha256((sha256(path) + json.dumps(ids)).encode()).hexdigest()[:20]
    cache = Path(root) / "data/cache" / namespace
    cache.mkdir(parents=True, exist_ok=True)
    sheet = cache / f"{key}.jpg"
    contact_sheet(candidates, {pid: str(p) for pid, p in reference_paths.items()}, sheet)
    return {"key": key, "images": [str(Path(path).resolve()), str(sheet.resolve())], "prompt": prompt,
            "candidate_ids": ids, "input_sha256": sha256(path), "images_sha256": [sha256(path), sha256(sheet)],
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def run_visual_requests(root, requests, namespace):
    from .experiments import save
    from .vlm_worker import cache_matches
    root = Path(root)
    python = root / ".venv-vlm/bin/python"
    if not python.is_file():
        raise RuntimeError("Local visual environment missing; follow the Apple Silicon VLM setup in README")
    cache = root / "data/cache" / namespace
    cache.mkdir(parents=True, exist_ok=True)
    request_path, response_path = cache / "requests.json", cache / "responses.json"
    config = {"model": MODEL, "revision": REVISION, "max_pixels": 1048576, "max_tokens": 256, "requests": requests}
    old = json.loads(response_path.read_text()) if response_path.exists() else {}
    reusable = old.get("responses", []) if old.get("model") == MODEL and old.get("revision") == REVISION else []
    cache_hits = {r["key"] for r in requests if any(cache_matches(response, r, config) for response in reusable)}
    save(request_path, config)
    # Model load plus generation; a hung worker must not pin the serving thread forever.
    subprocess.run([str(python), str(root / "partsid/vlm_worker.py"), str(request_path), str(response_path)],
                   check=True, timeout=VISUAL_TIMEOUT_S + VISUAL_TIMEOUT_PER_REQUEST_S * len(requests))
    output = json.loads(response_path.read_text())
    responses = {r["key"]: r for r in output["responses"]}
    decisions = []
    for request in requests:
        response = responses[request["key"]]
        decision = validate_response(response["raw"], request["candidate_ids"])
        decision.update(generation_ms=response["ms"], generation_tokens=response["generation_tokens"],
                        prompt_sha256=request["prompt_sha256"], images_sha256=request["images_sha256"],
                        cache_reused=request["key"] in cache_hits)
        decisions.append(decision)
    return decisions, {**{k: output[k] for k in ("model", "revision", "runtime", "model_load_s")},
                       "actual_new_generations": len(requests)-len(cache_hits), "validated_cached_generations": len(cache_hits)}


def verify_live(pipeline, record, path):
    if can_accept_sql(record):
        result = copy.deepcopy(record)
        result["rankings"]["gated"] = list(result["rankings"]["shape"])
        result["decision"] = {"used_vlm": False, "actual_vlm_executed": False, "reason": "唯一明确 SQL 型号且无视图冲突，跳过视觉模型"}
        return result
    request = prepare_visual(pipeline.root, record, path, pipeline.parts, pipeline.reference_paths, "sqlite_live_vlm")
    decisions, metadata = run_visual_requests(pipeline.root, [request], "sqlite_live_vlm")
    result = apply_visual(record, decisions[0])
    result["visual_runtime"] = metadata
    return result
