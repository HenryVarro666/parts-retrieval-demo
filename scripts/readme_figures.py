"""Generate bilingual parts-retrieval README diagrams; no third-party dependency."""
import argparse
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"


def text(x, y, value, size=16, color="#244a45", weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'


def box(x, y, w, h, fill="#fff", stroke="#d7e3da", radius=14):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'


def arrow(x1, y1, x2, y2, color="#72a18b"):
    return f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"/>'


def svg(title, description, body, h):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="{h}" viewBox="0 0 1120 {h}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="#72a18b"/></marker></defs>
<rect width="1120" height="{h}" rx="20" fill="#f4f7f1"/>
<g font-family="-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans CJK SC',sans-serif">{body}</g></svg>\n'''


def workflow(zh):
    title = "从元件照片到可检查的候选" if zh else "From part photos to inspectable candidates"
    stages = [("01", "同一元件 · 1–3 张照片", "逐图保留 OCR 原文与文字框", "近重复照片共享一票"),
              ("02", "多关键词召回", "RapidOCR → SQLite / FTS5", "SigLIP 补充外观候选"),
              ("03", "形状与多图排名融合", "形状可靠时作软提示", "固定 RRF · 候选不超过 10"),
              ("04", "可选视觉核验", "强型号门控 / 联合 Qwen-VL", "候选内选择或弃权 · 留依据")] if zh else [
              ("01", "One part · 1–3 photos", "Keep raw OCR text and boxes per view", "Near-duplicate groups share a vote"),
              ("02", "Keyword retrieval", "RapidOCR → SQLite / FTS5", "SigLIP adds appearance candidates"),
              ("03", "Shape & rank fusion", "Use reliable shape as a soft cue", "Fixed RRF · At most 10 candidates"),
              ("04", "Optional visual check", "Strong-ID gate / joint Qwen-VL", "Choose within pool or abstain")]
    body=text(32,45,title,25,weight=650)
    body+=text(32,73,"目录信息用于推理，评估标签只用于评分" if zh else "Catalog fields are inference inputs; evaluation labels are scoring-only",13,"#678077")
    for i,(number,heading,line1,line2) in enumerate(stages):
        x=28+i*274; body+=box(x,106,246,173)
        body+=text(x+18,138,number,14,"#21836c",650)+text(x+18,173,heading,17,weight=650)
        body+=text(x+18,213,line1,12)+text(x+18,248,line2,12,"#678077")
        if i<3: body+=arrow(x+250,191,x+268,191)
    body+=box(28,301,1066,44,"#e4efe6",stroke="none",radius=8)
    body+=text(48,328,"观察文字、SQL 命中、候选来源、模型原文与计时一起展示；排名分数不是正确概率。" if zh else "Inspect OCR, SQL hits, candidate origins, raw model reasoning and timing. Ranking scores are not probabilities.",14)
    return svg(title,"Local photo retrieval workflow with optional visual verification, no evaluation-label input",body,369)


def architecture(zh):
    title="本地架构与证据边界" if zh else "Local architecture & evidence boundaries"
    body=text(32,45,title,25,weight=650)
    def card(x,y,w,h,heading,lines,fill="#fff"):
        result=box(x,y,w,h,fill)+text(x+18,y+33,heading,18,weight=650)
        for i,line in enumerate(lines): result+=text(x+18,y+65+i*25,line,13,"#59756a")
        return result
    body+=card(28,83,292,165,"证据网页" if zh else "Evidence workbench",["HTML / CSS / JavaScript", "中文 / English / Español", "回放与实时推理明确分开" if zh else "Saved playback versus live inference"])
    body+=card(398,83,324,165,"本地 HTTP 服务" if zh else "Local HTTP service",["Python standard-library server", "目录/来源校验 · 模型延迟载入" if zh else "Catalog/provenance checks · Lazy models", "临时上传图，不写入评估数据" if zh else "Temporary uploads, outside the dataset"])
    body+=card(800,83,294,165,"冻结的公开证据" if zh else "Frozen public evidence",["Catalog SQLite + JSON / CSV", "来源/许可 · OCR/模型输出 · 结果" if zh else "Sources/licenses, OCR/model outputs", "标签仅评分，不进入推理" if zh else "Labels for scoring, not inference"])
    body+=arrow(325,165,388,165)+arrow(727,165,790,165)
    body+=card(28,300,510,140,"逐图检索与融合" if zh else "Per-view retrieval & fusion",["RapidOCR / EasyOCR · SigLIP · SQLite · NumPy", "形状未知可用性 · 固定 RRF · 冲突与来源保留" if zh else "Shape availability · Fixed RRF · Conflicts and evidence retained"],"#e9f1e9")
    body+=card(584,300,510,140,"独立的可选 VLM 环境" if zh else "Isolated optional VLM environment",["Qwen3-VL-4B · MLX · Apple Silicon", "联合多图 + 打乱的参考图；可弃权，失败保留原排序" if zh else "Joint views + shuffled references; abstain or retain original ranking"],"#e9f1e9")
    body+=arrow(504,253,282,289)+arrow(614,253,839,289)
    body+=text(32,478,"没有训练或外部推理 API；上传、模型权重与运行缓存不入 Git；公开评估数据带署名入库。" if zh else "No training or external inference API. Uploads/weights/runtime caches stay out of Git; attributed public evaluation data are included.",13,"#678077")
    return svg(title,"Browser, local Python service, frozen data and isolated optional model boundary",body,505)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--check",action="store_true"); args=parser.parse_args()
    ASSETS.mkdir(parents=True,exist_ok=True)
    for name,generator in [("workflow",workflow),("architecture",architecture)]:
        for lang in ["zh","en"]:
            path=ASSETS/f"{name}.{lang}.svg"; expected=generator(lang=="zh")
            if args.check:
                if not path.is_file() or path.read_text()!=expected: raise SystemExit(f"Outdated diagram: {path}")
            else: path.write_text(expected,encoding="utf-8")
    print("4 SVG diagrams verified" if args.check else "4 SVG diagrams rendered")


if __name__=="__main__": main()
