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


def decode_uploads(payload):
    if ("image" in payload) == ("images" in payload):
        raise ValueError("Supply image or images, exclusively")
    values = payload.get("images") if "images" in payload else [payload["image"]]
    if not isinstance(values, list) or not 1 <= len(values) <= 3:
        raise ValueError("Use one to three photos")
    images = [decode_upload(value) for value in values]
    if sum(image.width * image.height for image in images) > 48_000_000:
        raise ValueError("Total images exceed 48 megapixels")
    return images


def allowed_images(root=ROOT, requested=None):
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        allowed = {r["file"] for r in csv.DictReader(f)}
    manifest = root / "data/multi_image/manifest.json"
    if manifest.exists():
        allowed.update(p["file"] for g in json.loads(manifest.read_text()).get("groups", []) for p in g.get("photos", []))
    if requested in allowed:
        return allowed
    for run in multi_payload(root):
        allowed.update(p["file"] for pair in run["records"] for p in pair["record"]["photos"])
    return allowed


def multi_payload(root=ROOT):
    from .multi_image_experiments import validate_saved
    runs = []
    for path in sorted((root / "results/multi_image").glob("*.json")):
        doc = json.loads(path.read_text())
        if doc.get("schema") != 1:
            continue
        try:
            validate_saved(doc, root)
        except ValueError:
            continue
        runs.append({"name": path.stem, "scope": doc["scope"], "visual_enabled": doc["visual_enabled"], "force_visual": doc.get("force_visual", False),
                     "summary": doc["summary"], "setup_ms": doc.get("retrieval_setup_ms"),
                     "records": [] if doc["scope"] == "duplicate_control" else doc["records"]})
    return runs


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
    from .translation import translation_payload
    return {"runs": runs, "samples": samples, "catalog": catalog, "records": records,
            "prose_translations": translation_payload(root), "multi_image_runs": multi_payload(root)}


def translate(payload):
    from .translation import translate_texts
    with _lock:
        return translate_texts(payload.get("texts"), payload.get("language"), ROOT)


def predict(payload):
    images = decode_uploads(payload)
    engine, multiview = payload.get("engine", "rapidocr"), payload.get("multiview", False)
    if engine not in ("easyocr", "rapidocr") or not isinstance(multiview, bool):
        raise ValueError("Unknown OCR configuration")
    pipeline_name = payload.get("pipeline", "sqlite")
    verify_visual = payload.get("verify_visual", False)
    if pipeline_name not in ("sqlite", "legacy") or not isinstance(verify_visual, bool) or (pipeline_name == "legacy" and verify_visual):
        raise ValueError("Unknown retrieval or visual-verification configuration")
    if pipeline_name == "legacy" and len(images) > 1:
        raise ValueError("Legacy retrieval supports a single photo only")
    started = time.perf_counter()
    with _lock:
        if pipeline_name == "sqlite":
            from .candidate_pipeline import make_candidate_pipeline
            from .multi_image import compare_paths
            setup_started = time.perf_counter()
            key = (engine, multiview)
            if key not in _candidate_pipes:
                _candidate_pipes[key] = make_candidate_pipeline(ROOT, engine, multiview)
            pipe = _candidate_pipes[key]
            setup_ms = (time.perf_counter()-setup_started)*1000
            with tempfile.TemporaryDirectory(prefix="partsid-sqlite-upload-") as directory:
                paths = [Path(directory) / f"query-{i}.png" for i in range(len(images))]
                for image, path in zip(images, paths):
                    image.save(path)
                output = compare_paths(pipe, paths, verify_visual)
            return {**output, "catalog": web_payload()["catalog"], "live": True,
                    "setup_ms": setup_ms, "request_ms": (time.perf_counter()-started)*1000,
                    "channel": "gated" if verify_visual else "shape",
                    "timing": "measured live paired inference; loaded retrieval models shared; single first; VLM process/load included"}
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
            images[0].save(path)
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
                requested = query.get("file", [""])[0]
                path = dataset_path(requested, ROOT / "data", allowed_images(ROOT, requested))
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
                    is_png = path.suffix.lower() == ".png"
                    image.save(output, format="PNG" if is_png else "JPEG", **({} if is_png else {"quality": 92}))
                return self.respond(200, output.getvalue(), "image/png" if is_png else "image/jpeg")
            if parsed.path in ("/", "/index.html", "/app.js", "/i18n.js", "/multi_image.js", "/style.css"):
                name = "index.html" if parsed.path == "/" else parsed.path[1:]
                mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "i18n.js": "text/javascript; charset=utf-8", "multi_image.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
                return self.respond(200, (ROOT / "web" / name).read_bytes(), mime)
            self.respond(404, {"error": "Not found"})
        except (ValueError, FileNotFoundError):
            self.respond(400, {"error": "Invalid dataset image or request"})

    def do_POST(self):
        path = urlparse(self.path).path
        is_translation = path == "/api/translate"
        if path not in ("/api/predict", "/api/translate"):
            return self.respond(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.respond(403, {"error": "Cross-origin request rejected"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "Use application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 65536 if is_translation else MAX_UPLOAD * 4 + 4096
            if not 0 < length <= limit:
                return self.respond(413, {"error": "Translation request too large" if is_translation else "Image request too large"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Invalid payload")
            return self.respond(200, translate(payload) if is_translation else predict(payload))
        except (ValueError, TypeError):
            self.respond(400, {"error": "Invalid translation request" if is_translation else "Invalid image request"})
        except Exception as exc:
            print(f"{'Translation' if is_translation else 'Prediction'} failed: {type(exc).__name__}: {exc}", flush=True)
            self.respond(503 if is_translation else 500, {"error": "Local translation unavailable" if is_translation else "Local inference failed. Check the server log and optional model dependencies."})


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
