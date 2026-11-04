"""Loopback-first evidence workbench: measured playback and lazy live OCR.

The server has no authentication. It binds to 127.0.0.1 unless ``--host`` is
given explicitly, and it never serves files outside ``web/`` and the allow-listed
dataset images.
"""
import argparse
import base64
import binascii
import csv
import hashlib
import io
import ipaddress
import json
import logging
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 10 * 1024 * 1024
SOCKET_TIMEOUT_S = 120  # Drop half-open clients instead of pinning a handler thread forever.
STATIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "i18n.js": "text/javascript; charset=utf-8",
    "multi_image.js": "text/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}
CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                           "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
                           "form-action 'self'; frame-ancestors 'none'")
UPLOAD_PREFIXES = frozenset({"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64",
                             "data:application/octet-stream;base64", "data:;base64"})
UPLOAD_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LIVE_CACHE_KEEP = 50  # Most recent live visual-verification namespaces retained under data/cache/multi_live.
log = logging.getLogger("partsid.web")
_lock = threading.Lock()
_pipes = {}
_candidate_pipes = {}
_multi_validation_cache = {}
_multi_validation_lock = threading.Lock()


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
        # Browsers report an empty MIME type for some files; the decoded container is what counts.
        if prefix not in UPLOAD_PREFIXES:
            raise ValueError("Use a JPEG, PNG or WebP image")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_UPLOAD:
            raise ValueError("Image must be at most 10 MB")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in UPLOAD_FORMATS:
                raise ValueError("Use a JPEG, PNG or WebP image")
            if image.width * image.height > 16_000_000:
                raise ValueError("Image exceeds 16 megapixels")
            return ImageOps.exif_transpose(image).convert("RGB")
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, SyntaxError,
            Image.DecompressionBombError) as exc:
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


_allowed_cache = {}
_allowed_lock = threading.Lock()


def _allowed_key(root):
    """Cheap change detector for every input of the image allow-list."""
    paths = [root / "data/labels.csv", root / "data/multi_image/manifest.json",
             *sorted((root / "results/multi_image").glob("*.json"))]
    key = []
    for path in paths:
        try:
            stat = path.stat()
            key.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            key.append((str(path), None, None))
    return tuple(key)


def allowed_images(root=ROOT, requested=None):
    """Dataset images the server may serve: labelled files plus photos of validated saved runs.

    Validating saved runs hashes every dependency, so the full set is cached until any
    input file changes. An unknown filename therefore cannot trigger that work per request.
    """
    with open(root / "data/labels.csv", encoding="utf-8") as f:
        allowed = {r["file"] for r in csv.DictReader(f)}
    manifest = root / "data/multi_image/manifest.json"
    if manifest.exists():
        allowed.update(p["file"] for g in json.loads(manifest.read_text()).get("groups", []) for p in g.get("photos", []))
    if requested in allowed:
        return allowed
    key = (str(root.resolve()), _allowed_key(root))
    with _allowed_lock:
        cached = _allowed_cache.get(key)
    if cached is None:
        cached = set(allowed)
        for run in multi_payload(root):
            cached.update(p["file"] for pair in run["records"] for p in pair["record"]["photos"])
        with _allowed_lock:
            _allowed_cache.clear()
            _allowed_cache[key] = frozenset(cached)
    return allowed | cached


def multi_payload(root=ROOT):
    from .multi_image_experiments import replay_fingerprint, validate_saved
    runs = []
    for path in sorted((root / "results/multi_image").glob("*.json")):
        try:
            raw = path.read_bytes()
            doc = json.loads(raw)
        except (OSError, ValueError) as exc:
            log.warning("Skipping unreadable saved run %s: %s", path.name, exc)
            continue
        if not isinstance(doc, dict) or doc.get("schema") != 1:
            continue
        try:
            key = (str(root.resolve()), str(path.resolve()))
            digest = hashlib.sha256(raw).hexdigest()
            with _multi_validation_lock:
                # Enumerate logical dependencies independently of the stored hash list.
                # Include resolved targets so symlink retargeting also invalidates hits.
                fingerprint = (digest, replay_fingerprint(doc, root))
                if _multi_validation_cache.get(key) != fingerprint:
                    validate_saved(doc, root)
                    if fingerprint != (digest, replay_fingerprint(doc, root)):
                        raise ValueError("Replay dependencies changed during validation")
                    _multi_validation_cache[key] = fingerprint
        except (ValueError, OSError):
            continue
        runs.append({"name": path.stem, "scope": doc["scope"], "visual_enabled": doc["visual_enabled"], "force_visual": doc.get("force_visual", False),
                     "cohort": doc.get("cohort"), "groups": doc["groups"], "strata_summary": doc.get("strata_summary"),
                     "summary": doc["summary"], "setup_ms": doc.get("retrieval_setup_ms"),
                     "records": [] if doc["scope"] == "duplicate_control" else doc["records"]})
    return runs


def catalog_payload(root=ROOT):
    """Public catalog records joined with their reference photo; cheap enough for every request."""
    data = Path(root) / "data"
    parts = json.loads((data / "parts.json").read_text())
    with open(data / "labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    catalog = {p["id"]: dict(p) for p in parts}
    for row in rows:
        if row["split"] == "catalog":
            catalog[row["part_id"]].update(catalog_file=row["file"], **{k: row.get(k, "") for k in ("artist", "license", "page_url")})
    return catalog, rows


def web_payload(root=ROOT):
    data = root / "data"
    catalog, rows = catalog_payload(root)
    review_path = data / "reviews/error_review_2026-10-30.json"
    reviews = json.loads(review_path.read_text()).get("reviews", []) if review_path.exists() else []
    by_file = {r["image_path"].removeprefix("data/"): r for r in reviews}
    samples = [{**row, "gt": row["part_id"], "review": by_file.get(row["file"])} for row in rows if row["split"] == "query"]
    docs = []
    for path in sorted((root / "results/experiments").glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            log.warning("Skipping unreadable experiment %s: %s", path.name, exc)
            continue
        if isinstance(doc, dict) and "records" in doc and "name" in doc:
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
            request_ms = (time.perf_counter()-started)*1000
            if verify_visual:
                prune_live_cache(ROOT)
            return {**output, "catalog": catalog_payload(ROOT)[0], "live": True,
                    "setup_ms": setup_ms, "request_ms": request_ms,
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
        return {"record": result, "catalog": catalog_payload(ROOT)[0], "live": True, "channel": "fused"}


def prune_live_cache(root=ROOT, keep=LIVE_CACHE_KEEP):
    """Keep only the newest live visual namespaces; each request uses a unique one, so old ones are never reused."""
    directory = Path(root) / "data/cache/multi_live"
    if not directory.is_dir():
        return 0
    entries = sorted((entry for entry in directory.iterdir() if entry.is_dir()), key=lambda entry: entry.stat().st_mtime)
    removed = 0
    for entry in entries[:max(0, len(entries) - keep)]:
        shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    return removed


class Handler(BaseHTTPRequestHandler):
    timeout = SOCKET_TIMEOUT_S
    server_version = "partsid-workbench"
    sys_version = ""  # Do not advertise the interpreter version.
    # Host names a browser may use to reach this service. Anything else is a DNS-rebinding
    # or misdirected request and is refused before any data is read or returned.
    allowed_hosts = LOOPBACK_HOSTS

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by BaseHTTPRequestHandler
        log.info("%s %s", self.address_string(), format % args)

    def _hostname(self, value):
        try:
            return (urlparse("//" + value).hostname or "").lower()
        except ValueError:
            return ""

    def _host_allowed(self):
        host = self.headers.get("Host")
        return host is not None and self._hostname(host) in self.allowed_hosts

    def _safe_respond(self, status, body):
        try:
            self.respond(status, body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            log.info("client disconnected before the %s response was sent", status)

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if not self._host_allowed():
                return self._safe_respond(421, {"error": "Unexpected Host header"})
            self._get(urlparse(self.path))
        except (ValueError, FileNotFoundError):
            self._safe_respond(400, {"error": "Invalid dataset image or request"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            log.info("client disconnected during GET")
        except Exception:
            log.exception("GET %s failed", self.path)
            self._safe_respond(500, {"error": "Local workbench request failed. Check the server log."})

    def _get(self, parsed):
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
        name = "index.html" if parsed.path == "/" else parsed.path[1:]
        if name in STATIC_FILES:
            return self.respond(200, (ROOT / "web" / name).read_bytes(), STATIC_FILES[name])
        self.respond(404, {"error": "Not found"})

    def do_POST(self):
        is_translation = False
        try:
            if not self._host_allowed():
                return self._safe_respond(421, {"error": "Unexpected Host header"})
            path = urlparse(self.path).path
            is_translation = path == "/api/translate"
            if path not in ("/api/predict", "/api/translate"):
                return self.respond(404, {"error": "Not found"})
            origin = self.headers.get("Origin")
            if origin and (origin.lower() == "null" or self._hostname(urlparse(origin).netloc) not in self.allowed_hosts
                           or urlparse(origin).netloc != self.headers.get("Host")):
                return self.respond(403, {"error": "Cross-origin request rejected"})
            if self.headers.get_content_type() != "application/json":
                return self.respond(415, {"error": "Use application/json"})
            length = int(self.headers.get("Content-Length", "0"))
            limit = 65536 if is_translation else MAX_UPLOAD * 4 + 4096
            if not 0 < length <= limit:
                return self.respond(413, {"error": "Translation request too large" if is_translation else "Image request too large"})
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Truncated request body")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Invalid payload")
            return self.respond(200, translate(payload) if is_translation else predict(payload))
        except (ValueError, TypeError):
            self._safe_respond(400, {"error": "Invalid translation request" if is_translation else "Invalid image request"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            log.info("client disconnected during POST")
        except Exception:
            log.exception("%s failed", "Translation" if is_translation else "Prediction")
            self._safe_respond(503 if is_translation else 500, {"error": "Local translation unavailable" if is_translation else "Local inference failed. Check the server log and optional model dependencies."})


def is_loopback(host):
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address; anything but loopback exposes an unauthenticated service")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allowed-host", action="append", default=[], metavar="NAME",
                        help="additional Host name browsers may use (repeatable); loopback names are always allowed")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    args.allowed_hosts = frozenset(LOOPBACK_HOSTS | {args.host.lower()} | {name.lower() for name in args.allowed_host})
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not is_loopback(args.host):
        log.warning("Binding to %s exposes an unauthenticated service to the network; "
                    "put it behind an authenticating reverse proxy.", args.host)
    Handler.allowed_hosts = args.allowed_hosts
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    log.info("Parts evidence workbench: http://%s:%s", args.host, server.server_port)
    print(f"Parts evidence workbench: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopping on keyboard interrupt")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
