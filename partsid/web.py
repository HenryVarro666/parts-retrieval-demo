"""Loopback-only evidence workbench: measured playback and lazy live OCR."""
import argparse
import base64
import binascii
import csv
import io
import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 10 * 1024 * 1024
_lock = threading.Lock()
_pipes = {}
_candidate_pipes = {}


def dataset_path(rel, data, allowed):
    if not isinstance(rel, str) or rel not in allowed:
        raise ValueError("Unknown dataset image")
    path = (data / rel).resolve()
    if not path.is_relative_to(data.resolve()) or not path.is_file():
        raise ValueError("Invalid dataset image")
    return path


def decode_upload(value):
    if not isinstance(value, str) or len(value) > MAX_UPLOAD * 4 // 3 + 256:
        raise ValueError("Image must be at most 10 MB")
    try:
        prefix, encoded = value.split(",", 1)
        if prefix not in ("data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"):
            raise ValueError("Use a JPEG, PNG or WebP image")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_UPLOAD:
            raise ValueError("Image must be at most 10 MB")
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("Image exceeds 16 megapixels")
            return ImageOps.exif_transpose(image).convert("RGB")
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid image: use a JPEG, PNG or WebP up to 10 MB / 16 megapixels") from exc


def web_payload(root=ROOT):
    data = root / "data"
    parts = json.loads((data / "parts.json").read_text())
    with open(data / "labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    catalog = {p["id"]: dict(p) for p in parts}
    for row in rows:
        if row["split"] == "catalog":
            catalog[row["part_id"]].update(catalog_file=row["file"], **{k: row.get(k, "") for k in ("artist", "license", "page_url")})
    review_path = data / "reviews/error_review_2026-10-30.json"
    reviews = json.loads(review_path.read_text()).get("reviews", []) if review_path.exists() else []
    by_file = {r["image_path"].removeprefix("data/"): r for r in reviews}
    samples = [{**row, "gt": row["part_id"], "review": by_file.get(row["file"])} for row in rows if row["split"] == "query"]
    docs = []
    for path in sorted((root / "results/experiments").glob("*.json")):
        doc = json.loads(path.read_text())
        if "records" in doc and "name" in doc:
            docs.append(doc)
    runs, records = [], {}
    baseline = next((d for d in docs if d["name"] == "easyocr_whole"), None)
    before = {r["file"]: r["rankings"]["fused"][0] == r["gt"] for r in baseline["records"]} if baseline else {}
    for doc in docs:
        info = {k: doc.get(k) for k in ("name", "status", "config", "summary", "channel")}
        info["label"] = {"easyocr_whole": "EasyOCR · 原始基线", "easyocr_views": "EasyOCR · 多视图", "rapidocr_whole": "PP-OCRv6 · 整图", "rapidocr_views": "PP-OCRv6 · 多视图", "qwen_vlm_top10": "Qwen-VL · Top-10 核验"}.get(doc["name"], doc.get("label", doc["name"]))
        if before and info.get("summary"):
            pairs = [(before[r["file"]], bool(r["rankings"][doc["channel"]]) and r["rankings"][doc["channel"]][0] == r["gt"])
                     for r in doc["records"] if r["file"] in before]
            info["summary"].update(wins=sum(not a and b for a, b in pairs), regressions=sum(a and not b for a, b in pairs))
        runs.append(info)
        records[doc["name"]] = {r["file"]: r for r in doc["records"]}
    return {"runs": runs, "samples": samples, "catalog": catalog, "records": records}


def predict(payload):
    image = decode_upload(payload.get("image"))
    engine, multiview = payload.get("engine", "rapidocr"), payload.get("multiview", False)
    if engine not in ("easyocr", "rapidocr") or not isinstance(multiview, bool):
        raise ValueError("Unknown OCR configuration")
    pipeline_name = payload.get("pipeline", "sqlite")
    verify_visual = payload.get("verify_visual", False)
    if pipeline_name not in ("sqlite", "legacy") or not isinstance(verify_visual, bool) or (pipeline_name == "legacy" and verify_visual):
        raise ValueError("Unknown retrieval or visual-verification configuration")
    started = time.perf_counter()
    with _lock:
        if pipeline_name == "sqlite":
            from .candidate_pipeline import make_candidate_pipeline, verify_live
            key = (engine, multiview)
            if key not in _candidate_pipes:
                _candidate_pipes[key] = make_candidate_pipeline(ROOT, engine, multiview)
            pipe = _candidate_pipes[key]
            with tempfile.TemporaryDirectory(prefix="partsid-sqlite-upload-") as directory:
                path = Path(directory) / "query.png"
                image.save(path)
                result = pipe.run(path)
                if verify_visual:
                    result = verify_live(pipe, result, path)
            result["ms"]["total"] = (time.perf_counter()-started)*1000
            return {"record": result, "catalog": web_payload()["catalog"], "live": True,
                    "channel": "gated" if verify_visual else "shape",
                    "timing": "measured live end-to-end including requested VLM process/model loading"}
        from .experiments import make_pipeline
        key = (engine, multiview)
        if key not in _pipes:
            # Encoders/index are shared; only OCR views change.
            if _pipes:
                from .evaluate import Pipeline
                from .evidence_ocr import EvidenceOCR
                old = next(iter(_pipes.values()))
                _pipes[key] = Pipeline(old.parts, old.index, EvidenceOCR(engine, old.device, old.parts, multiview=multiview), old.text_enc, old.image_enc, old.device)
            else:
                _pipes[key] = make_pipeline(engine, multiview)[0]
        pipe = _pipes[key]
        with tempfile.TemporaryDirectory(prefix="partsid-upload-") as directory:
            path = Path(directory) / "query.png"
            image.save(path)
            result = pipe.run(path)
            result["evidence"] = pipe.ocr.last_result
        return {"record": result, "catalog": web_payload()["catalog"], "live": True, "channel": "fused"}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/data":
                return self.respond(200, web_payload())
            if parsed.path == "/api/image":
                query = parse_qs(parsed.query)
                with open(ROOT / "data/labels.csv", encoding="utf-8") as f:
                    allowed = {r["file"] for r in csv.DictReader(f)}
                path = dataset_path(query.get("file", [""])[0], ROOT / "data", allowed)
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    if "crop" in query:
                        crop = [int(x) for x in query["crop"][0].split(",")]
                        if len(crop) != 4 or not (0 <= crop[0] < crop[2] <= image.width and 0 <= crop[1] < crop[3] <= image.height):
                            raise ValueError("Invalid crop")
                        image = image.crop(crop)
                    angle = int(query.get("rotation", ["0"])[0])
                    if angle not in (0, 90, 180, 270):
                        raise ValueError("Invalid rotation")
                    image = image.rotate(angle, expand=True)
                    output = io.BytesIO()
                    image.save(output, format="JPEG", quality=92)
                return self.respond(200, output.getvalue(), "image/jpeg")
            if parsed.path in ("/", "/index.html", "/app.js", "/style.css"):
                name = "index.html" if parsed.path == "/" else parsed.path[1:]
                mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
                return self.respond(200, (ROOT / "web" / name).read_bytes(), mime)
            self.respond(404, {"error": "Not found"})
        except (ValueError, FileNotFoundError):
            self.respond(400, {"error": "Invalid dataset image or request"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/predict":
            return self.respond(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.respond(403, {"error": "Cross-origin request rejected"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "Use application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD * 4 // 3 + 1024:
                return self.respond(413, {"error": "Image request too large"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Invalid payload")
            return self.respond(200, predict(payload))
        except (ValueError, TypeError):
            self.respond(400, {"error": "Invalid image request"})
        except Exception as exc:
            print(f"Prediction failed: {type(exc).__name__}: {exc}", flush=True)
            self.respond(500, {"error": "Local inference failed. Check the server log and optional model dependencies."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Parts evidence workbench: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
