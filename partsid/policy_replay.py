"""Offline replay of two ranking-rule changes on frozen evidence (PR-034, PR-035).

Everything is read from saved experiment records: OCR text and boxes per view,
SQLite/appearance retrieval, shape descriptors and the VLM decisions already
generated for the saved candidate pools. Only pure Python and the committed
SQLite catalog run; no OCR, embedding or visual-model inference happens. The
numbers are therefore policy projections on the same frozen inputs and are
labelled as replay, never as fresh measurements or new timings.

    python -I -m partsid.policy_replay          # writes results/policy_replay/
"""
import copy
import csv
import hashlib
import json
from pathlib import Path

from . import identifier
from .candidate_experiments import validate_source
from .candidate_pipeline import apply_visual, merge_candidates, shape_rerank
from .multi_image import apply_group_visual, can_accept_group, fuse_records
from .multi_image_experiments import validate_saved
from .rerank import summarize
from .shape import compare_shapes
from .sqlite_catalog import SQLiteCatalog

ROOT = Path(__file__).resolve().parent.parent
POLICIES = {
    "frozen": {"shape_policy": "frozen", "digit_policy": "frozen",
               "label": "冻结规则（回放对照）"},
    "pr034_neutral_shape": {"shape_policy": "neutral", "digit_policy": "frozen",
                            "label": "PR-034 形状未知中性"},
    "pr035_digit_guard": {"shape_policy": "frozen", "digit_policy": "guard",
                          "label": "PR-035 纯数字批号不作精确命中"},
    "both": {"shape_policy": "neutral", "digit_policy": "guard", "label": "两项合并"},
}
SINGLE_SOURCE = "results/experiments/sqlite_vlm.json"
PAIRED_SOURCES = {"retrieval": "results/multi_image/public_retrieval.json",
                  "selective": "results/multi_image/public_gated.json",
                  "forced": "results/multi_image/public_visual.json"}
REFERENCE_SHAPES = "results/candidates/reference_shapes.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FrozenEvidence:
    """Catalog, reference silhouettes and the read-only SQLite catalog of the frozen runs."""

    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.parts = json.loads((self.root / "data/parts.json").read_text())
        self.reference_shapes = json.loads((self.root / REFERENCE_SHAPES).read_text())["descriptors"]
        self.db = SQLiteCatalog(self.root / "data/catalog.sqlite")

    def select_view(self, views, threshold, digit_policy):
        """Replay EvidenceOCR's view selection and strong-ID conflict rule on saved views."""
        strong_views, scored = {}, []
        for view in views:
            hits = identifier.rank(view["text"], self.parts, digit_policy=digit_policy)
            strong = [part for part, score, _ in hits if score >= identifier.FOLDED]
            for part in strong:
                strong_views.setdefault(part, []).append(view["id"])
            retained = [b for b in view["boxes"] if b["confidence"] >= threshold]
            mean_confidence = sum(b["confidence"] for b in retained) / len(retained) if retained else 0.0
            scored.append((int(len(strong) == 1), float(hits[0][1]) if hits else 0.0, mean_confidence))
        selected = max(range(len(views)), key=lambda i: scored[i])
        conflicts = ([{"part_id": part, "views": ids} for part, ids in sorted(strong_views.items())]
                     if len(strong_views) > 1 else [])
        return views[selected], conflicts

    def replay_single(self, record, threshold, policy):
        """Rebuild sql/hybrid/shape rankings for one saved single-photo record under a policy."""
        shape_policy, digit_policy = policy["shape_policy"], policy["digit_policy"]
        views = record["evidence"]["views"]
        view, conflicts = self.select_view(views, threshold, digit_policy)
        selection_changed = view["id"] != record["evidence"]["selected_view"]
        if selection_changed:
            boxes = [{**b, "view_id": view["id"]} for b in view["boxes"] if b["confidence"] >= threshold]
            retrieval = self.db.search(view["text"], limit=10, boxes=boxes)
        else:
            retrieval = {k: copy.deepcopy(record["retrieval"][k]) for k in ("keywords", "candidates", "strong_ids")}
        appearance = list(record["rankings"]["image"])
        pool = merge_candidates(retrieval["candidates"], appearance, retrieval["strong_ids"])
        ids = [p["part_id"] for p in pool]
        scores = {pid: compare_shapes(record["shape"]["query"], self.reference_shapes[pid]) for pid in ids}
        shape_ids = shape_rerank(ids, retrieval["strong_ids"], scores, shape_policy)
        replayed = copy.deepcopy(record)
        replayed["evidence"] = {**record["evidence"], "selected_view": view["id"], "text": view["text"],
                                "conflicts": conflicts}
        replayed["retrieval"] = {**retrieval, "pool": pool, "candidate_ids": ids,
                                 "sql_candidate_ids": [c["part_id"] for c in retrieval["candidates"]],
                                 "fallback_used": any("appearance" in p["origins"] for p in pool)}
        replayed["shape"] = {"query": record["shape"]["query"], "reference_scores": scores, "ranked_ids": shape_ids}
        replayed["rankings"] = {"sql": replayed["retrieval"]["sql_candidate_ids"], "hybrid": ids, "shape": shape_ids,
                                "image": appearance, "fused": shape_ids}
        replayed["ocr_text"] = view["text"]
        replayed["id_hits"] = identifier.rank(view["text"], self.parts, digit_policy=digit_policy)
        replayed["replay"] = {"selection_changed": selection_changed,
                              "pool_changed": set(ids) != set(record["retrieval"]["candidate_ids"])}
        for key in ("vlm", "decision"):
            replayed.pop(key, None)
        return replayed


def _channel_summary(rows, channel, baseline_rows=None):
    """Top-1/3/Recall@10 for a channel; latency fields are dropped because replay has none."""
    result = summarize(rows, channel)
    result.pop("latency_ms", None)
    if baseline_rows is not None:
        pairs = [(bool(b["rankings"][channel]) and b["rankings"][channel][0] == b["gt"],
                  bool(r["rankings"][channel]) and r["rankings"][channel][0] == r["gt"])
                 for b, r in zip(baseline_rows, rows)]
        result["wins_vs_frozen"] = sum(not before and after for before, after in pairs)
        result["regressions_vs_frozen"] = sum(before and not after for before, after in pairs)
    return result


def replay_queries(evidence, doc):
    """All 44 saved queries under every policy; VLM decisions reused only for unchanged pools."""
    threshold = doc["config"]["metadata"]["ocr"]["text_min_confidence"]
    output = {}
    for name, policy in POLICIES.items():
        rows = []
        for record in doc["records"]:
            replayed = evidence.replay_single(record, threshold, policy)
            replayed.update(file=record["file"], gt=record["gt"])
            if replayed["replay"]["pool_changed"]:
                # The saved visual decision saw a different candidate pool; nothing can be reused.
                replayed["rankings"]["reranked"] = None
                replayed["rankings"]["gated"] = None
                replayed["decision"] = {"used_vlm": None, "reason_code": "pool_changed_needs_new_vlm"}
            else:
                decision = record.get("vlm") or {"abstained": True, "selected_id": None}
                replayed = apply_visual(replayed, decision)
                replayed["decision"]["actual_vlm_executed"] = False
                replayed["decision"]["reason_code"] = "saved_decision_replayed"
            rows.append(replayed)
        output[name] = rows
    summaries = {}
    for name, rows in output.items():
        usable = [r for r in rows if r["rankings"]["gated"] is not None]
        baseline = output["frozen"]
        summary = {channel: _channel_summary(rows, channel, baseline) for channel in ("sql", "hybrid", "shape")}
        usable_baseline = [b for b, r in zip(baseline, rows) if r["rankings"]["gated"] is not None]
        summary["gated_reusable"] = {**_channel_summary(usable, "gated", usable_baseline), "n_pool_changed": len(rows) - len(usable)}
        summary["selection_changed"] = sum(r["replay"]["selection_changed"] for r in rows)
        summary["pool_changed"] = sum(r["replay"]["pool_changed"] for r in rows)
        summary["conflicts"] = sum(bool(r["evidence"]["conflicts"]) for r in rows)
        # Any reordering at all, so "no Top-k change" is distinguishable from "rule never fired".
        summary["shape_ranking_changed"] = sum(
            r["rankings"]["shape"] != b["rankings"]["shape"] for r, b in zip(rows, baseline))
        summary["id_hits_changed"] = sum(r["id_hits"] != b["id_hits"] for r, b in zip(rows, baseline))
        summary["shape_available"] = sum(bool(r["shape"]["query"].get("available")) for r in rows)
        summary["unknown_reference_in_pool"] = sum(
            any(v is None for v in r["shape"]["reference_scores"].values()) for r in rows)
        summaries[name] = summary
    fidelity = {"records": len(doc["records"]),
                "frozen_replay_matches_saved_shape_ranking": sum(
                    r["rankings"]["shape"] == s["rankings"]["shape"] for r, s in zip(output["frozen"], doc["records"])),
                "frozen_replay_matches_saved_shape_scores": sum(
                    r["shape"]["reference_scores"] == s["shape"]["reference_scores"]
                    for r, s in zip(output["frozen"], doc["records"]))}
    return {"summaries": summaries, "fidelity": fidelity,
            "records": {name: [{"file": r["file"], "gt": r["gt"], "rankings": r["rankings"], "replay": r["replay"],
                                "selected_view": r["evidence"]["selected_view"], "conflicts": r["evidence"]["conflicts"],
                                "decision": r.get("decision")} for r in rows] for name, rows in output.items()}}


def replay_paired(evidence, docs):
    """First-photo and three-photo rankings for the 8 public groups under every policy."""
    results = {}
    for mode, doc in docs.items():
        threshold = doc["pipeline"]["ocr"]["text_min_confidence"]
        per_policy = {}
        for name, policy in POLICIES.items():
            rows = []
            for pair in doc["records"]:
                saved = pair["record"]
                photos = sorted(saved["photos"], key=lambda p: p["index"])
                replayed_photos = [evidence.replay_single(p["record"], threshold, policy) for p in photos]
                groups = [p["group"] for p in photos]
                single = fuse_records(replayed_photos[:1], groups[:1], policy["shape_policy"])
                multi = fuse_records(replayed_photos, groups, policy["shape_policy"])
                row = {"object_id": pair["object_id"], "gt": pair["gt"], "paths": {}}
                for label, fused, source in (("single", single, pair["baseline_record"]), ("multi", multi, saved)):
                    fused["evidence"] = dict(fused.get("evidence", {}))
                    fused.setdefault("fusion", {"photo_count": 1})
                    pool_changed = set(fused["retrieval"]["candidate_ids"]) != set(source["retrieval"]["candidate_ids"])
                    status = "retrieval_only"
                    if mode != "retrieval":
                        accepted = can_accept_group(fused) and mode != "forced"
                        if accepted:
                            fused["rankings"]["gated"] = list(fused["rankings"]["shape"])
                            status = "gate_accepted"
                        elif pool_changed or not source.get("vlm"):
                            fused["rankings"]["gated"] = None
                            status = "pool_changed_needs_new_vlm" if pool_changed else "no_saved_decision"
                        else:
                            fused = apply_group_visual(fused, source["vlm"])
                            status = "saved_decision_replayed"
                    ids = fused["rankings"].get("gated") if mode != "retrieval" else fused["rankings"]["shape"]
                    row["paths"][label] = {"status": status, "pool_changed": pool_changed,
                                           "top10": ids[:10] if ids else None,
                                           "selection_changed": [p["replay"]["selection_changed"] for p in
                                                                 (replayed_photos[:1] if label == "single" else replayed_photos)]}
                rows.append(row)
            per_policy[name] = rows
        summary = {}
        for name, rows in per_policy.items():
            entry = {}
            entry["multi_ranking_changed"] = sum(
                r["paths"]["multi"]["top10"] != f["paths"]["multi"]["top10"]
                for r, f in zip(rows, per_policy["frozen"]))
            for label in ("single", "multi"):
                usable = [r for r in rows if r["paths"][label]["top10"] is not None]
                ranks = [r["paths"][label]["top10"].index(r["gt"]) + 1 if r["gt"] in r["paths"][label]["top10"] else 999 for r in usable]
                frozen = {r["object_id"]: r["paths"][label]["top10"] for r in per_policy["frozen"][:]}
                before = {oid: bool(ids) and ids[0] == gt for oid, ids, gt in
                          ((r["object_id"], frozen[r["object_id"]], r["gt"]) for r in usable)}
                entry[label] = {"n": len(usable), "unavailable": len(rows) - len(usable),
                                "top1_k": sum(k <= 1 for k in ranks), "top3_k": sum(k <= 3 for k in ranks),
                                "recall10_k": sum(k <= 10 for k in ranks),
                                "wins_vs_frozen": sum((not before[r["object_id"]]) and k == 1 for r, k in zip(usable, ranks)),
                                "regressions_vs_frozen": sum(before[r["object_id"]] and k != 1 for r, k in zip(usable, ranks))}
            summary[name] = entry
        fidelity = sum(1 for r, pair in zip(per_policy["frozen"], doc["records"])
                       if r["paths"]["multi"]["top10"] == pair["comparison"]["multi"]["top10"][:10]
                       and r["paths"]["single"]["top10"] == pair["comparison"]["single"]["top10"][:10])
        results[mode] = {"source": PAIRED_SOURCES[mode], "summary": summary, "records": per_policy,
                         "fidelity": {"records": len(doc["records"]), "frozen_replay_matches_saved": fidelity}}
    return results


def run(root=ROOT, out_dir=None):
    """Replay every policy over the saved evidence and write comparison.json/.md to out_dir.

    out_dir defaults to results/policy_replay under root; the test suite writes to a temporary
    directory and checks that the committed files are reproduced byte for byte.
    """
    root = Path(root)
    evidence = FrozenEvidence(root)
    single_doc = json.loads((root / SINGLE_SOURCE).read_text())
    validate_source(single_doc, root)
    paired_docs = {}
    for mode, rel in PAIRED_SOURCES.items():
        doc = json.loads((root / rel).read_text())
        validate_saved(doc, root)
        paired_docs[mode] = doc
    queries = replay_queries(evidence, single_doc)
    paired = replay_paired(evidence, paired_docs)
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        query_count = sum(1 for r in csv.DictReader(f) if r["split"] == "query")
    report = {"date": "2026-11-04", "schema": 1, "replay": True, "new_inference": False,
              "policies": {name: {k: v for k, v in p.items()} for name, p in POLICIES.items()},
              "rules": {
                  "pr034_neutral_shape": "shape_rerank/fuse_records: a candidate without a reference silhouette receives the mean shape RRF contribution of the known candidates instead of none",
                  "pr035_digit_guard": "identifier: a digit-only alias found inside a longer run of digits (a lot number, also after a word join), or any all-digit join of OCR words, is not an exact/folded hit; SQLite retrieval is unchanged, so only view selection, conflicts and id_hits move"},
              "sources": {"single": {"path": SINGLE_SOURCE, "sha256": sha256(root / SINGLE_SOURCE), "queries": query_count},
                          **{mode: {"path": rel, "sha256": sha256(root / rel)} for mode, rel in PAIRED_SOURCES.items()},
                          "reference_shapes": {"path": REFERENCE_SHAPES, "sha256": sha256(root / REFERENCE_SHAPES)},
                          "catalog_sqlite_sha256": sha256(root / "data/catalog.sqlite")},
              "vlm_policy": "saved decisions are replayed only when the candidate pool is identical to the saved one; a changed pool is counted separately and not scored",
              "single_queries": queries, "paired_groups": paired}
    directory = Path(out_dir) if out_dir is not None else root / "results/policy_replay"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "comparison.md").write_text(render(report) + "\n", encoding="utf-8")
    return report


def render(report):
    q = report["single_queries"]
    lines = ["# PR-034 / PR-035 规则回放（冻结证据，无新推理）", "",
             f"来源：`{report['sources']['single']['path']}`（{report['sources']['single']['queries']} 查询）与 3 份公开三图记录。"
             "回放只重新执行纯 Python 规则与只读 SQLite；OCR 文本、外观相似度、形状描述和已保存的视觉模型判断原样复用。"
             "没有耗时数据，也不是新的实测。", "",
             f"冻结规则回放保真：{q['fidelity']['frozen_replay_matches_saved_shape_ranking']}/{q['fidelity']['records']} 条形状排序与保存记录一致，"
             f"{q['fidelity']['frozen_replay_matches_saved_shape_scores']}/{q['fidelity']['records']} 条形状分数一致。", "",
             "## 44 张查询", "",
             "| 策略 | SQL Top-1 | 补召回 Top-1 | 形状 Top-1 / Top-3 | 门控 Top-1（可复用判断 / 池改变） | 形状排序有变化 | 视图选择变化 | 冲突 | 形状 修复/退步 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, s in q["summaries"].items():
        g = s["gated_reusable"]
        lines.append(f"| {report['policies'][name]['label']} | {s['sql']['top1_k']}/{s['sql']['n']} | {s['hybrid']['top1_k']}/{s['hybrid']['n']} | "
                     f"{s['shape']['top1_k']}/{s['shape']['n']} / {s['shape']['top3_k']}/{s['shape']['n']} | "
                     f"{g['top1_k']}/{g['n']}（{g['n_pool_changed']} 池改变） | {s['shape_ranking_changed']} | {s['selection_changed']} | {s['conflicts']} | "
                     f"{s['shape'].get('wins_vs_frozen', 0)} / {s['shape'].get('regressions_vs_frozen', 0)} |")
    first = next(iter(q["summaries"].values()))
    lines += ["", f"查询形状可用 {first['shape_available']}/{first['shape'].get('n')}；候选池含无参考形状目录类的查询 {first['unknown_reference_in_pool']}/{first['shape'].get('n')}。"]
    lines += ["", "## 8 组公开三图（第一张 → 三张）", ""]
    for mode, result in report["paired_groups"].items():
        lines += [f"### {mode}（`{result['source']}`，冻结回放与保存结果一致 {result['fidelity']['frozen_replay_matches_saved']}/{result['fidelity']['records']}）", "",
                  "| 策略 | 单图 Top-1 | 三图 Top-1 | 单图 Top-3 → 三图 Top-3 | 三图排序有变化 | 不可评分（池改变/无判断） | 修复/退步（三图） |", "|---|---:|---:|---:|---:|---:|---:|"]
        for name, s in result["summary"].items():
            a, b = s["single"], s["multi"]
            lines.append(f"| {report['policies'][name]['label']} | {a['top1_k']}/{a['n']} | {b['top1_k']}/{b['n']} | {a['top3_k']} → {b['top3_k']} | {s['multi_ranking_changed']} | "
                         f"{a['unavailable']} / {b['unavailable']} | {b['wins_vs_frozen']} / {b['regressions_vs_frozen']} |")
        lines.append("")
    lines += ["视觉判断只在候选池与保存时完全相同时复用；池改变的查询不计分并单独计数，评估它们需要新的 VLM 推理。",
              "本回放不改变已发布结果与默认规则；是否采用两条规则需结合独立实物验证。"]
    return "\n".join(lines)


if __name__ == "__main__":
    report = run()
    print(render(report))
