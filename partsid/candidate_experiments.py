"""Build SQLite and measure fresh OCR / keyword / shape / new-pool VLM stages."""
import argparse
import copy
import csv
import hashlib
import json
import time
from pathlib import Path

from .candidate_pipeline import (ROOT, MODEL, REVISION, make_candidate_pipeline, prepare_visual,
                                 run_visual_requests, apply_visual, sha256)
from .experiments import save
from .rerank import summarize

STAGES = {"sqlite_keywords": ("sql", "SQLite · 多关键词"), "sqlite_hybrid": ("hybrid", "SQLite · 视觉补召回"),
          "sqlite_shape": ("shape", "SQLite · 形状重排"), "sqlite_vlm": ("reranked", "SQLite · 新候选视觉核验"),
          "sqlite_gated": ("gated", "SQLite · 明确型号优先核验")}


def manifest(root):
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    queries = [r for r in rows if r["split"] == "query"]
    expected = {r["file"]: r["part_id"] for r in queries}
    if not queries or len(expected) != len(queries):
        raise ValueError("Query manifest must be nonempty and unique")
    refs = {r["part_id"]: r["file"] for r in rows if r["split"] == "catalog"}
    return expected, refs


def validate_rows(rows, root, allow_partial=False):
    expected, _ = manifest(root)
    files = [r.get("file") for r in rows]
    if len(files) != len(set(files)) or not set(files).issubset(expected) or (not allow_partial and set(files) != set(expected)):
        raise ValueError("Stage records are partial, duplicated or misaligned with the query manifest")
    if any(r.get("gt") != expected[r["file"]] for r in rows):
        raise ValueError("Stage labels disagree with the query manifest")


def validate_source(doc, root):
    if doc.get("status") != "complete":
        raise ValueError("Complete source inference is required")
    validate_rows(doc["records"], root)
    expected, references = manifest(root)
    config = doc["config"]
    for key, file in (("labels_sha256", "labels.csv"), ("database_sha256", "catalog.sqlite")):
        if config.get(key) != sha256(root / "data" / file):
            raise ValueError(f"Stale source fingerprint: {file}; rerun inference")
    hashes = config.get("query_image_sha256", {})
    if set(hashes) != set(expected) or any(hashes[file] != sha256(root / "data" / file) for file in expected):
        raise ValueError("Query image fingerprints changed; rerun inference")
    metadata = config["metadata"]
    parts = json.loads((root / "data/parts.json").read_text())
    canonical_parts = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if metadata["sqlite"].get("catalog_sha256") != hashlib.sha256(canonical_parts).hexdigest():
        raise ValueError("Catalog source fingerprint changed; rebuild and rerun inference")
    ref_hashes = metadata.get("reference_image_sha256", {})
    if set(ref_hashes) != set(references) or any(ref_hashes[pid] != sha256(root / "data" / file) for pid, file in references.items()):
        raise ValueError("Reference image fingerprints changed; rerun inference")
    canonical_refs = json.dumps(sorted(references.items()), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if metadata["sqlite"].get("references_sha256") != hashlib.sha256(canonical_refs).hexdigest():
        raise ValueError("Reference manifest fingerprint changed; rebuild and rerun inference")


def build(root=ROOT):
    from .sqlite_catalog import build_catalog
    parts = json.loads((root / "data/parts.json").read_text())
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        references = [{"part_id": r["part_id"], "file": r["file"]} for r in csv.DictReader(f) if r["split"] == "catalog"]
    path = root / "data/catalog.sqlite"
    metadata = build_catalog(parts, path, references)
    save(root / "data/catalog_manifest.json", {"date": "2026-10-31", "metadata": metadata,
                                             "source_file_sha256": sha256(root / "data/parts.json"),
                                             "database_sha256": sha256(path)})
    print(f"SQLite built: {metadata['part_count']} parts, {metadata['reference_count']} reference images", flush=True)


def stage_summary(rows, channel):
    result = summarize(rows, channel)
    result["recall5_k"] = sum(r["gt"] in r["rankings"][channel][:5] for r in rows)
    result["recall5"] = result["recall5_k"] / len(rows) if rows else None
    result["coverage"] = sum(bool(r["rankings"][channel]) for r in rows) / len(rows) if rows else None
    return result


def stage_document(name, records, config, root=ROOT, complete=True):
    validate_rows(records, root, allow_partial=not complete)
    channel, label = STAGES[name]
    rows = copy.deepcopy(records)
    for row in rows:
        if channel in ("sql", "hybrid", "shape"):
            relevant = {"sql": ["ocr", "sqlite"], "hybrid": ["ocr", "sqlite", "image"],
                        "shape": ["ocr", "sqlite", "image", "shape"]}[channel]
            row["ms"] = {key: row["ms"][key] for key in relevant}
            row["ms"]["total"] = row["stage_totals"][channel]
        if channel == "gated" and not row["decision"]["used_vlm"]:
            row.pop("vlm", None)  # Projected gate does not present unused evidence as consulted.
        row["rankings"]["fused"] = row["rankings"][channel]
    doc = {"name": name, "label": label, "date": "2026-10-31", "channel": channel,
           "status": "complete" if complete else "running", "config": copy.deepcopy(config),
           "summary": stage_summary(rows, channel), "records": rows}
    doc["summary"]["shape_available"] = sum(r["shape"]["query"]["available"] for r in rows)
    if channel in ("reranked", "gated"):
        doc["summary"]["abstained"] = sum(r.get("vlm", {}).get("abstained", False) for r in rows)
        doc["summary"]["vlm_calls"] = len(rows) if channel == "reranked" else sum(r["decision"]["used_vlm"] for r in rows)
        doc["summary"]["batch_verified_queries"] = len(rows)
        doc["summary"]["actual_batch_vlm_calls"] = config.get("visual_runtime", {}).get("actual_new_generations", len(rows))
        doc["summary"]["validated_cached_generations"] = config.get("visual_runtime", {}).get("validated_cached_generations", 0)
    save(root / "results/experiments" / f"{name}.json", doc)
    return doc


def run(root=ROOT):
    from .evaluate import upright_path
    build(root)
    pipeline = make_candidate_pipeline(root)
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        queries = [r for r in csv.DictReader(f) if r["split"] == "query"]
    paths = {q["file"]: upright_path(q["file"]) for q in queries}
    pipeline.run(paths[queries[0]["file"]])
    rows = []
    config = {"scope": "all_queries_fresh_staged_inference", "metadata": pipeline.metadata,
              "labels_sha256": sha256(root / "data/labels.csv"), "database_sha256": sha256(root / "data/catalog.sqlite"),
              "query_image_sha256": {q["file"]: sha256(root / "data" / q["file"]) for q in queries},
              "timing": "measured fresh cumulative OCR/SQLite/appearance/shape stages; one untimed query warmup; model loading excluded"}
    stage_document("sqlite_shape", [], config, root, complete=False)
    try:
        for i, query in enumerate(queries):
            row = pipeline.run(paths[query["file"]])
            # Labels are attached only after all inference and candidate decisions.
            row.update(file=query["file"], gt=query["part_id"])
            rows.append(row)
            stage_document("sqlite_shape", rows, config, root, complete=False)
            print(f"SQLite fresh pipeline: {i+1}/{len(queries)}", flush=True)
    except Exception as exc:
        failed = json.loads((root / "results/experiments/sqlite_shape.json").read_text())
        failed.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save(root / "results/experiments/sqlite_shape.json", failed)
        raise
    for name in ("sqlite_keywords", "sqlite_hybrid", "sqlite_shape"):
        stage_document(name, rows, config, root)
    save(root / "results/candidates/reference_shapes.json", {
        "date": "2026-10-31", "descriptors": pipeline.reference_shapes,
        "reference_image_sha256": pipeline.metadata["reference_image_sha256"]})


def vlm(root=ROOT):
    from .evaluate import upright_path
    doc = json.loads((root / "results/experiments/sqlite_shape.json").read_text())
    validate_source(doc, root)
    parts = {p["id"]: p for p in json.loads((root / "data/parts.json").read_text())}
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        references = {r["part_id"]: root / "data" / r["file"] for r in csv.DictReader(f) if r["split"] == "catalog"}
    requests, prepare_times = [], []
    for row in doc["records"]:
        start = time.perf_counter()
        requests.append(prepare_visual(root, row, upright_path(row["file"]), parts, references, "sqlite_batch_vlm_v1"))
        prepare_times.append((time.perf_counter()-start)*1000)
    decisions, metadata = run_visual_requests(root, requests, "sqlite_batch_vlm_v1")
    validate_source(doc, root)
    rows = []
    for old, decision, preparation_ms in zip(doc["records"], decisions, prepare_times):
        row = apply_visual(old, decision)
        row["ms"]["verification_prepare"] = preparation_ms
        row["ms"]["vlm"] = decision["generation_ms"]
        row["ms"]["total"] += preparation_ms + decision["generation_ms"]
        rows.append(row)
    config = {**doc["config"], "model": MODEL, "revision": REVISION, "visual_runtime": metadata,
              "candidate_source_sha256": sha256(root / "results/experiments/sqlite_shape.json"),
              "timing": "fresh OCR/database/shape stage time + separately measured new-pool VLM generation and preparation; model load excluded; not end-to-end"}
    stage_document("sqlite_vlm", rows, config, root)
    gated_rows = copy.deepcopy(rows)
    for row in gated_rows:
        if not row["decision"]["used_vlm"]:
            row["ms"].pop("vlm", None)
            row["ms"].pop("verification_prepare", None)
            row["ms"]["total"] = row["stage_totals"]["shape"]
    config["timing"] = "gate projection from fresh staged measurements; VLM invoked in full batch; estimated stage sum, not end-to-end"
    stage_document("sqlite_gated", gated_rows, config, root)


def compare(root=ROOT):
    out = root / "results/experiments"
    original = json.loads((out / "easyocr_whole.json").read_text())
    rapid = json.loads((out / "rapidocr_views.json").read_text())
    lookup = {"baseline": {r["file"]: r for r in original["records"]}, "rapid": {r["file"]: r for r in rapid["records"]}}
    docs = [json.loads((out / f"{name}.json").read_text()) for name in STAGES if (out / f"{name}.json").exists()]
    docs = [d for d in docs if d["status"] == "complete"]
    for doc in docs:
        validate_source(doc, root)
    query_count = len(manifest(root)[0])
    lines = ["# SQLite 多关键词、形状与新候选视觉核验", "", f"原基线Top-1：27/44 (61.4%)；新OCR多视图：38/44；旧门控离线重放：40/44。本轮{query_count}张开发图，旧标签与目录未修改。", "",
             "| 阶段 | Top-1 | Top-3 | Recall@5 | Recall@10 | 相对新OCR修复 / 退步 | p50 / p95 ms |", "|---|---|---|---|---|---|---|"]
    for doc in docs:
        s, channel = doc["summary"], doc["channel"]
        for name, old in lookup.items():
            pairs = [(old[r["file"]]["rankings"]["fused"][0] == r["gt"],
                      bool(r["rankings"][channel]) and r["rankings"][channel][0] == r["gt"]) for r in doc["records"]]
            s[f"wins_vs_{name}"] = sum(not before and after for before, after in pairs)
            s[f"regressions_vs_{name}"] = sum(before and not after for before, after in pairs)
        lat = s["latency_ms"]
        lines.append(f"| {doc['label']} | {s['top1_k']}/{s['n']} | {s['top3_k']}/{s['n']} | {s['recall5_k']}/{s['n']} | {s['recall10_k']}/{s['n']} | {s['wins_vs_rapid']} / {s['regressions_vs_rapid']} | {lat['p50']:.0f} / {lat['p95']:.0f} |")
    lines += ["", "SQL-only召回率只统计关键词/别名/厂商/描述命中的候选。视觉补召回明确标记来源：SQL前5 + SigLIP外观前5，去重并补足至10；不把外观候选算成数据库命中。", "",
              "形状为固定阈值的前景轮廓启发式，使用细长度、凸实度、圆度。无可靠掩膜时不提供形状评分；未估计物理尺寸、封装名称或引脚数。形状仅软重排且保护明确型号，不排除同型号不同封装。", "",
              "前三阶段来自重新运行的RapidOCR/SQLite/外观/形状流水线。新VLM使用新的候选、拼图、形状提示和独立缓存命名空间，未复用旧EasyOCR Top-10判断；其时间是新阶段耗时与单独测量的生成耗时之和，不含模型加载，不是一个端到端服务计时。", "",
              "门控行是新实测输出上的门控投影：完整VLM批次仍处理44张，仅在唯一明确SQL型号无视图冲突时投影跳过。实际实时网页已实现相同跳过/调用规则；不能把投影时延当作新部署吞吐。小样本开发集与非专家标签限制结论。"]
    directory = root / "results/candidates"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(directory / "comparison.json", {"date": "2026-10-31", "runs": [{k:d[k] for k in ("name", "label", "config", "summary")} for d in docs]})
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "run", "vlm", "compare", "all"])
    args = parser.parse_args()
    if args.mode == "build":
        build()
    if args.mode in ("run", "all"):
        run()
    if args.mode in ("vlm", "all"):
        vlm()
    if args.mode in ("compare", "all"):
        compare()


if __name__ == "__main__":
    main()
