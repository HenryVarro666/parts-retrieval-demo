"""Fixed-rule OCR/VLM combinations replayed from saved model outputs.

Decision functions never read labels. No model dependencies or new inference
are needed: python -m partsid.ensemble replays the checked-in 44-query outputs.
"""
import argparse
import copy
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .fusion import rrf
from .rerank import summarize

SOURCES = ("easyocr_whole", "easyocr_views", "rapidocr_whole", "rapidocr_views", "qwen_vlm_top10")
POLICIES = ("ensemble_vote5", "ensemble_family_vote", "ensemble_rrf", "ensemble_strong_gate", "ensemble_disagreement_gate")
LABELS = {"ensemble_vote5": "五路等票", "ensemble_family_vote": "模型家族各一票", "ensemble_rrf": "OCR / VLM 排名融合",
          "ensemble_strong_gate": "明确型号优先 · 按需核验", "ensemble_disagreement_gate": "双 OCR 分歧时核验"}
RAPID = "rapidocr_views"
VLM = "qwen_vlm_top10"
ROOT = Path(__file__).resolve().parent.parent


def _vlm_id(record):
    decision = record.get("vlm", {})
    selected = decision.get("selected_id")
    return selected if (decision.get("abstained") is False and isinstance(selected, str)
                        and selected in record["rankings"]["fused"][:10]) else None


def _strong(record):
    strong = {hit[0] for hit in record.get("id_hits", []) if hit[1] >= 0.9}
    return (len(strong) == 1 and record["rankings"]["fused"][0] in strong
            and not record.get("evidence", {}).get("conflicts"))


def decide(records: dict, policy: str) -> dict:
    """Combine predictions only; gt/marking/review are deliberately unused."""
    if policy not in POLICIES:
        raise ValueError(f"Unknown combination policy: {policy}")
    primary = records[RAPID]["rankings"]["fused"]
    visual = _vlm_id(records[VLM])
    experts = ["easyocr_whole", RAPID]
    called, chosen_source = True, "combined"
    if policy == "ensemble_vote5":
        experts = list(SOURCES[:-1])
    elif policy == "ensemble_strong_gate":
        experts = [RAPID]
        called = not _strong(records[RAPID])
    elif policy == "ensemble_disagreement_gate":
        called = records["easyocr_whole"]["rankings"]["fused"][0] != primary[0]
    votes = [{"expert": expert, "candidate": records[expert]["rankings"]["fused"][0], "abstained": False}
             for expert in experts]
    if called:
        votes.append({"expert": VLM, "candidate": visual, "abstained": visual is None})
    if policy in ("ensemble_strong_gate", "ensemble_disagreement_gate"):
        chosen = visual if called and visual else primary[0]
        chosen_source = VLM if called and visual else RAPID
        ranking = [chosen] + [pid for pid in primary if pid != chosen]
        reason = ("OCR 已满足固定接受条件，未调用视觉模型" if not called
                  else "OCR 证据不足或分支分歧，采用视觉核验" if visual
                  else "视觉模型弃权，保留新 OCR 的排序")
    elif policy == "ensemble_rrf":
        inputs = {expert: records[expert]["rankings"]["fused"] for expert in experts}
        inputs[VLM] = [visual] if visual else []
        ranking = [pid for pid, _ in rrf(inputs)]
        reason = "两路 OCR 的 Top-10 排名等权 RRF 融合；视觉模型只贡献选中型号"
    else:
        counts = Counter(v["candidate"] for v in votes if v["candidate"] is not None)
        preference = {pid: i for i, pid in enumerate(primary)}
        candidates = set(primary) | set(counts)
        ranking = sorted(candidates, key=lambda pid: (-counts[pid], preference.get(pid, len(primary)), pid))
        reason = "按票数排序；平票依新 OCR 多视图名次，再依型号 ID"
    return {"ranking": ranking, "votes": votes, "vlm_called": called, "chosen_source": chosen_source,
            "reason": reason, "policy": policy, "vote_counts": dict(Counter(v["candidate"] for v in votes if v["candidate"] is not None))}


def estimate_ms(records, policy, decision):
    """Serial sum of required complete OCR branches plus any VLM generation.

    Each branch is counted once; no unimplemented shared-encoder optimization
    or parallel scheduling is assumed. Abstaining generation still costs time.
    """
    required = {v["expert"] for v in decision["votes"] if v["expert"] != VLM}
    if decision["vlm_called"]:
        required.add("easyocr_whole")  # Frozen baseline candidate generation.
    total = sum(records[source]["ms"]["total"] for source in required)
    if decision["vlm_called"]:
        total += records[VLM]["vlm"]["generation_ms"]
    return total


def validate_inputs(docs, expected):
    aligned = {file: {} for file in expected}
    for source in SOURCES:
        doc = docs[source]
        rows = doc.get("records", [])
        files = [row["file"] for row in rows]
        if doc.get("status") != "complete" or len(files) != len(set(files)) or set(files) != set(expected):
            raise ValueError(f"Incomplete or misaligned input: {source}")
        for row in rows:
            if row.get("gt") != expected[row["file"]]:
                raise ValueError(f"Inconsistent ground truth in {source}")
            ranking = row.get("rankings", {}).get("fused", [])
            if not ranking or len(ranking) != len(set(ranking)) or not all(isinstance(pid, str) for pid in ranking):
                raise ValueError(f"Malformed input ranking: {source}")
            aligned[row["file"]][source] = row
    return aligned


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(root=ROOT):
    out = root / "results/experiments"
    paths = {name: out / f"{name}.json" for name in SOURCES}
    docs = {name: json.loads(path.read_text()) for name, path in paths.items()}
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        expected = {r["file"]: r["part_id"] for r in csv.DictReader(f) if r["split"] == "query"}
    aligned = validate_inputs(docs, expected)
    provenance = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    output = []
    for policy in POLICIES:
        rows = []
        for _file, sources in aligned.items():
            decision = decide(sources, policy)
            row = copy.deepcopy(sources[RAPID])
            row["rankings"]["ensemble"] = decision["ranking"]
            row["rankings"]["original_baseline"] = sources["easyocr_whole"]["rankings"]["fused"]
            row["ensemble"] = {key: value for key, value in decision.items() if key != "ranking"}
            # OCR boxes always belong to the displayed RapidOCR view. VLM evidence is separate.
            if decision["vlm_called"]:
                row["vlm"] = copy.deepcopy(sources[VLM]["vlm"])
                row["vlm"]["candidate_source"] = "easyocr_whole frozen Top-10"
            row["ms"] = {"total": estimate_ms(sources, policy, decision)}
            row["ensemble"]["cost_note"] = "离线完整分支串行耗时估算，未实测端到端"
            rows.append(row)
        summary = summarize(rows, "ensemble", "original_baseline")
        rapid_pairs = summarize(rows, "ensemble", "fused")
        summary.update(wins_vs_rapid=rapid_pairs["wins"], regressions_vs_rapid=rapid_pairs["regressions"],
                       vlm_calls=sum(r["ensemble"]["vlm_called"] for r in rows))
        doc = {"name": policy, "label": LABELS[policy], "date": "2026-10-30", "status": "complete", "channel": "ensemble",
               "config": {"scope": "all_queries_offline_combination_replay", "policy": policy,
               "sources_sha256": provenance, "labels_sha256": hashlib.sha256((root / "data/labels.csv").read_bytes()).hexdigest(),
               "timing": "estimated serial stage sum from saved complete OCR branches plus called VLM generation; no model load, not end-to-end",
               "inference_rerun": False,
               "tie_rule": "best single-channel rank then ID" if policy == "ensemble_rrf" else "RapidOCR views order then ID",
               "weights_fitted": False},
               "summary": summary, "records": rows}
        _write(out / f"{policy}.json", doc)
        output.append(doc)
    report = root / "results/ensembles"
    lines = ["# OCR / VLM 固定规则组合实验", "", "全部44张查询；模型输出保持冻结，组合规则在重放前固定。未重新推理，未按真值拟合权重。", "",
             "| 方案 | Top-1 | Top-3 | 相对新OCR修复 / 退步 | VLM调用 | 串行阶段合计估算 p50 / p95 |", "|---|---|---|---|---|---|"]
    for doc in output:
        s = doc["summary"]
        lines.append(f"| {doc['label']} | {s['top1_k']}/{s['n']} | {s['top3_k']}/{s['n']} | {s['wins_vs_rapid']} / {s['regressions_vs_rapid']} | {s['vlm_calls']}/{s['n']} | {s['latency_ms']['p50']:.0f} / {s['latency_ms']['p95']:.0f} ms |")
    lines += ["", "参考：原EasyOCR为27/44，新OCR多视图为38/44，全量视觉重排为39/44。相对新OCR的修复与退步均逐查询配对计算。", "",
              "五路等票将同一家族的整图/多视图重复计票；家族投票每个模型家族只取一个代表。平票优先新OCR多视图；这是一条明确的设计偏好，并非学出的概率。RRF使用k=60，VLM只贡献有效选中型号，不重复计算其继承的基线尾部排名。", "",
              "明确型号门控：仅当新OCR恰有一个exact/folded别名匹配（分数>=0.9）、与融合首选一致且不存在跨视图强型号冲突时跳过VLM；这个分数不是OCR正确概率。分歧门控先运行两路OCR，一致时跳过VLM。VLM弃权或选出候选集外ID时回退新OCR。", "",
              "VLM仍使用原EasyOCR冻结Top-10及原参考拼图；这次没有改变视觉输入或提示词。门控成本把生成该候选集所需的EasyOCR完整分支计入，只计一次；调用后即使VLM弃权仍计时。所有时间是已测完整分支的串行合计估算，未模拟共享编码优化或并行调度，不是新部署的端到端性能。", "",
              "这是已知44张开发图上的离线组合比较，不是新盲测。模型错误相关、样本小、标签未经领域专家验证。较好的开发集组合仍需独立照片验证，不能把事后最优选对器算作实际准确率。"]
    report.mkdir(parents=True, exist_ok=True)
    (report / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write(report / "comparison.json", {"date": "2026-10-30", "input_sha256": provenance,
                                      "runs": [{k: doc[k] for k in ("name", "label", "config", "summary")} for doc in output]})
    print("\n".join(lines))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    run(parser.parse_args().root)


if __name__ == "__main__":
    main()
