"""Reproducible, checkpointed experiments; never overwrite original reports."""
import argparse
import copy
import datetime
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from .rerank import apply_selection, build_prompt, summarize, validate_response

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "experiments"
VLM_MODEL = "mlx-community/Qwen3-VL-4B-Instruct-4bit"
VLM_REVISION = "2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def make_pipeline(engine="easyocr", multiview=False):
    from .device import pick_device
    from .embed import ImageEncoder, TextEncoder
    from .evaluate import DATA, Pipeline, build_index, load_labels, upright_path
    from .evidence_ocr import EvidenceOCR
    parts = json.loads((DATA / "parts.json").read_text())
    refs, queries = load_labels()
    device = pick_device(None)
    image_enc, text_enc = ImageEncoder(device), TextEncoder(device)
    paths = {r["file"]: upright_path(r["file"]) for r in refs + queries}
    index = build_index(parts, refs, paths, text_enc, image_enc)
    ocr = EvidenceOCR(engine, device, parts, multiview=multiview)
    return Pipeline(parts, index, ocr, text_enc, image_enc, device), refs, queries, paths


def run_ocr(engine, multiview=False, limit=None):
    name = engine + ("_views" if multiview else "_whole")
    if limit is not None:
        name += f"_smoke{limit}"
    path = OUT / f"{name}.json"
    if path.exists() and json.loads(path.read_text()).get("status") == "complete" and limit is None:
        print(f"Already complete: {name}", flush=True)
        return
    pipe, _, queries, paths = make_pipeline(engine, multiview)
    if limit:
        queries = queries[:limit]
    config = {"ocr": engine, "multiview": multiview, "metadata": pipe.ocr.metadata,
              "labels_sha256": digest(ROOT / "data/labels.csv"), "catalog_sha256": digest(ROOT / "data/parts.json"),
              "query_count": len(queries), "scope": "all_queries" if not limit else "smoke_subset",
              "timing": "one untimed query warmup, one measured pass; differs from original full second-pass timing"}
    doc = {"name": name, "date": datetime.date(2026, 10, 30).isoformat(), "status": "running", "config": config,
           "channel": "fused", "records": []}
    pipe.run(paths[queries[0]["file"]])
    try:
        for i, query in enumerate(queries):
            result = pipe.run(paths[query["file"]])
            result.update(file=query["file"], gt=query["part_id"], evidence=copy.deepcopy(pipe.ocr.last_result))
            doc["records"].append(result)
            doc["summary"] = summarize(doc["records"])
            save(path, doc)
            print(f"{name}: {i + 1}/{len(queries)} top1={doc['summary']['top1_k']}", flush=True)
    except Exception as exc:
        doc.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save(path, doc)
        raise
    doc.update(status="complete" if not limit else "smoke_subset", summary=summarize(doc["records"]))
    doc["summaries"] = {channel: summarize(doc["records"], channel) for channel in doc["records"][0]["rankings"]}
    doc["config"]["metadata"] = pipe.ocr.metadata
    save(path, doc)


def contact_sheet(candidates, refs, output):
    from PIL import Image, ImageDraw, ImageOps
    from .images import load_rgb
    cell_w, cell_h = 180, 155
    canvas = Image.new("RGB", (cell_w * 5, cell_h * 2), "white")
    draw = ImageDraw.Draw(canvas)
    for i, part in enumerate(candidates):
        x, y = (i % 5) * cell_w, (i // 5) * cell_h
        image = ImageOps.contain(load_rgb(ROOT / "data" / refs[part["id"]]), (170, 125))
        canvas.paste(image, (x + (cell_w - image.width) // 2, y + 20))
        draw.text((x + 6, y + 4), part["id"], fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def run_vlm(baseline="easyocr_whole", limit=None):
    import csv
    from .evaluate import upright_path
    source = OUT / f"{baseline}.json"
    base = json.loads(source.read_text())
    if base["status"] != "complete":
        raise ValueError("VLM requires a complete frozen baseline run")
    parts = {p["id"]: p for p in json.loads((ROOT / "data/parts.json").read_text())}
    with open(ROOT / "data/labels.csv") as f:
        refs = {r["part_id"]: r["file"] for r in csv.DictReader(f) if r["split"] == "catalog"}
    records = base["records"][:limit] if limit else base["records"]
    requests = []
    for row in records:
        ids = row["rankings"]["fused"][:10]
        shuffled = list(ids)
        random.Random(digest(ROOT / "data" / row["file"])).shuffle(shuffled)
        candidates = [parts[pid] for pid in shuffled]
        key = hashlib.sha256(row["file"].encode()).hexdigest()[:16]
        sheet = ROOT / "data/cache/vlm" / f"{key}.jpg"
        contact_sheet(candidates, refs, sheet)
        prompt = build_prompt(candidates)
        requests.append({"key": key, "images": [str(upright_path(row["file"])), str(sheet)],
                         "prompt": prompt, "candidate_ids": ids,
                         "input_sha256": digest(ROOT / "data" / row["file"]),
                         "images_sha256": [digest(upright_path(row["file"])), digest(sheet)],
                         "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
    cache = ROOT / "data/cache/vlm"
    request_path, response_path = cache / "requests.json", cache / "responses.json"
    save(request_path, {"model": VLM_MODEL, "revision": VLM_REVISION,
                        "max_pixels": 1048576, "max_tokens": 256, "requests": requests})
    subprocess.run([str(ROOT / ".venv-vlm/bin/python"), str(ROOT / "partsid/vlm_worker.py"),
                    str(request_path), str(response_path)], check=True)
    output = json.loads(response_path.read_text())
    responses = {r["key"]: r for r in output["responses"]}
    result = []
    for old, req in zip(records, requests):
        item = copy.deepcopy(old)
        response = responses[req["key"]]
        decision = validate_response(response["raw"], req["candidate_ids"])
        item["vlm"] = {**decision, "generation_ms": response["ms"],
                       "generation_tokens": response.get("generation_tokens"), "prompt_sha256": req["prompt_sha256"]}
        item["rankings"]["reranked"] = apply_selection(req["candidate_ids"], decision)
        item["ms"]["vlm"] = response["ms"]
        # A sum of separately measured stages, explicitly not one end-to-end service run.
        item["ms"]["total"] += response["ms"]
        result.append(item)
    doc = {"name": "qwen_vlm_top10", "date": "2026-10-30", "status": "complete" if not limit else "smoke_subset",
           "channel": "reranked", "config": {"baseline": baseline, "baseline_sha256": digest(source),
           "model": VLM_MODEL, "revision": VLM_REVISION, "max_pixels": 1048576, "max_tokens": 256,
           "model_load_s": output["model_load_s"], "runtime": output["runtime"],
           "scope": "all_queries" if not limit else "smoke_subset", "candidate_order": "deterministic image-hash shuffle",
           "timing": "cached baseline stage time + measured VLM generation; model load excluded; not end-to-end"},
           "summary": summarize(result, "reranked", "fused"), "records": result}
    doc["summary"]["abstained"] = sum(r["vlm"]["abstained"] for r in result)
    if limit is not None:
        doc["name"] += f"_smoke{limit}"
    save(OUT / f"{doc['name']}.json", doc)


def compare():
    docs = [json.loads(p.read_text()) for p in sorted(OUT.glob("*.json")) if p.name != "comparison.json"]
    docs = [d for d in docs if d.get("status") == "complete"]
    baseline = next((d for d in docs if d["name"] == "easyocr_whole"), None)
    lines = ["# OCR and Top-10 VLM development experiments", "", "44 query photos / 18 catalog classes; unchanged model-generated labels. This is development evaluation, not a new blind test.", "", "| Run | Top-1 | Top-3 | Recall@10 | Wins / regressions vs baseline | p50 / p95 ms |", "|---|---|---|---|---|---|"]
    for doc in docs:
        summary = doc["summary"]
        wins = losses = 0
        if baseline:
            old = {r["file"]: r for r in baseline["records"]}
            for r in doc["records"]:
                before = old[r["file"]]["rankings"]["fused"][0] == r["gt"]
                after = bool(r["rankings"][doc["channel"]]) and r["rankings"][doc["channel"]][0] == r["gt"]
                wins += after and not before
                losses += before and not after
        summary.update(wins=wins, regressions=losses)
        lat = summary["latency_ms"]
        lines.append(f"| {doc['name']} | {summary['top1_k']}/{summary['n']} | {summary['top3_k']}/{summary['n']} | {summary['recall10_k']}/{summary['n']} | {wins} / {losses} | {lat['p50']:.0f} / {lat['p95']:.0f} |")
    lines += ["", "OCR runs use one untimed query warmup and one measured pass. VLM timing sums cached baseline stage time and separately measured generation; it excludes model load and is not measured end-to-end. CPU ONNX OCR and MPS PyTorch OCR are different runtime paths.", "", "Whole versus views compares eight predefined views and catalog-guided view selection together. It does not isolate cropping from rotation or hypothesis selection. Neither labels nor catalog aliases were patched after inspecting errors. VLM sees only query pixels, shuffled candidate metadata and reference photos, never ground truth or review notes."]
    if any(doc.get("channel") == "ensemble" for doc in docs):
        lines += ["", "Ensemble rows are fixed-output offline policy replay, not new inference runs. Their times estimate a serial sum of the required saved complete OCR branches plus any called VLM generation, excluding model load; they are not measured end-to-end. See results/ensembles/comparison.md for policy definitions, calls and paired changes versus the new OCR."]
    (OUT / "comparison.md").write_text("\n".join(lines) + "\n")
    save(OUT / "comparison.json", {"date": "2026-10-30", "runs": [{k: d[k] for k in ("name", "status", "channel", "config", "summary")} for d in docs]})
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["ocr", "vlm", "compare"])
    parser.add_argument("--engine", default="rapidocr", choices=["easyocr", "rapidocr", "all"])
    parser.add_argument("--views", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.mode == "ocr":
        if args.engine == "all":
            for engine in ("easyocr", "rapidocr"):
                for views in (False, True):
                    run_ocr(engine, views, args.limit)
        else:
            run_ocr(args.engine, args.views, args.limit)
    elif args.mode == "vlm":
        run_vlm(limit=args.limit)
    else:
        compare()


if __name__ == "__main__":
    main()
