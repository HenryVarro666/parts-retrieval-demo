"""OCR adapters retaining view geometry and catalog-guided selection evidence.

The whole-image EasyOCR path deliberately keeps its original file decoder.
Transformed views use contiguous BGR arrays, the native array convention of
both engines. Callers should provide upright files, as the original evaluator
already does. Model scores and view heuristics are not calibrated confidence.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

from . import identifier
from .images import load_rgb
from .ocr import MIN_CONF


class EvidenceOCR:
    """Lazy local OCR with whole-image or eight deterministic alternative views.

    A preconfigured raw reader may be supplied as a callable accepting a BGR
    array and returning the selected engine's native result structure.
    Instances retain mutable last-result state; serialize access to an instance.
    """

    def __init__(self, name: str, device: str, parts: list[dict], multiview: bool = False,
                 *, raw_reader: Callable | None = None):
        if name not in {"easyocr", "rapidocr"}:
            raise ValueError(f"Unsupported OCR engine {name!r}; choose easyocr or rapidocr")
        self.name = name
        self.device = device
        # Only public catalog fields participate. No query labels are accepted.
        self.parts = [{"id": p["id"], "aliases": list(p["aliases"])} for p in parts]
        self.multiview = multiview
        self.last_result: dict | None = None
        self._reader = None
        self._raw_reader = raw_reader
        self._model_hashes: dict[str, str] = {}
        packages = ["easyocr", "torch"] if name == "easyocr" else ["rapidocr", "onnxruntime"]
        self.metadata = {
            "engine": name,
            "packages": {p: self._version(p) for p in packages},
            "requested_device": device,
            "runtime": device if name == "easyocr" else "onnxruntime CPU",
            "multiview": multiview,
            "catalog_guided_view_selection": bool(multiview),
            "selection_policy": "unique strong identifier, best identifier score, mean retained-box confidence, original order",
            "confidence_calibrated": False,
            "crop_policy": "whole plus center with floor(8% of each original dimension) removed per edge" if multiview else "whole image",
            "rotation_direction": "counterclockwise",
            "text_min_confidence": MIN_CONF if name == "easyocr" else 0.5,
            "input_policy": "EasyOCR original view uses native file path; all other views and RapidOCR use BGR arrays",
            "requires_upright_input": True,
            "model_files": [],
            "providers": [],
            "external_reader": raw_reader is not None,
        }
        if name == "rapidocr":
            self.metadata["model_config"] = {
                "detector": "PP-OCRv6 small multilingual",
                "classifier": "PP-OCRv4 mobile 0/180",
                "recognizer": "PP-OCRv6 small multilingual",
            }

    @staticmethod
    def _version(package: str) -> str | None:
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            return None

    def _ensure_reader(self) -> None:
        if self._raw_reader is not None or self._reader is not None:
            return
        try:
            if self.name == "easyocr":
                import easyocr
                self._reader = easyocr.Reader(["en"], gpu=self.device, quantize=False, verbose=False)
            else:
                from rapidocr import EngineType, ModelType, OCRVersion, RapidOCR
                self._reader = RapidOCR(params={
                    "Det.engine_type": EngineType.ONNXRUNTIME,
                    "Det.ocr_version": OCRVersion.PPOCRV6,
                    "Det.model_type": ModelType.SMALL,
                    "Rec.engine_type": EngineType.ONNXRUNTIME,
                    "Rec.ocr_version": OCRVersion.PPOCRV6,
                    "Rec.model_type": ModelType.SMALL,
                    "Cls.engine_type": EngineType.ONNXRUNTIME,
                    "EngineConfig.onnxruntime.use_cuda": False,
                    "EngineConfig.onnxruntime.use_coreml": False,
                    "EngineConfig.onnxruntime.use_dml": False,
                    "EngineConfig.onnxruntime.use_cann": False,
                })
        except ImportError as exc:
            hint = "uv sync --extra experiments" if self.name == "rapidocr" else "uv sync"
            raise RuntimeError(f"{self.name} dependencies are unavailable; run `{hint}`: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Could not initialize {self.name}: {exc}") from exc

    def _model_file(self, role: str, path) -> dict | None:
        if not path:
            return None
        path = Path(path)
        if not path.is_file():
            return None
        key = str(path)
        if key not in self._model_hashes:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            self._model_hashes[key] = digest.hexdigest()
        return {"role": role, "name": path.name, "sha256": self._model_hashes[key]}

    def _update_model_metadata(self) -> None:
        if self._raw_reader is not None:
            return
        files = []
        if self.name == "easyocr":
            folder = getattr(self._reader, "model_storage_directory", None)
            if folder:
                # Reader is explicitly configured for English and its default CRAFT detector.
                for role, filename in [("detector", "craft_mlt_25k.pth"), ("recognizer", "english_g2.pth")]:
                    item = self._model_file(role, Path(folder) / filename)
                    if item:
                        files.append(item)
        else:
            providers = set()
            for attr, role in [("text_det", "detector"), ("text_cls", "classifier"), ("text_rec", "recognizer")]:
                component = getattr(self._reader, attr, None)
                wrapper = getattr(component, "session", None)
                session = getattr(wrapper, "session", None)
                if session is not None:
                    item = self._model_file(role, getattr(session, "_model_path", None))
                    if item:
                        files.append(item)
                    providers.update(session.get_providers())
            self.metadata["providers"] = sorted(providers)
        self.metadata["model_files"] = files

    def _views(self, image: Image.Image):
        width, height = image.size
        crops = [("whole", (0, 0, width, height))]
        if self.multiview:
            dx, dy = math.floor(width * 0.08), math.floor(height * 0.08)
            crops.append(("center", (dx, dy, width - dx, height - dy)))
        for label, crop in crops:
            cropped = image.crop(crop)
            for rotation in ([0, 90, 180, 270] if self.multiview else [0]):
                view_image = cropped.rotate(rotation, expand=True) if rotation else cropped
                yield {
                    "id": f"{label}_r{rotation}", "crop": list(crop), "rotation": rotation,
                    "width": view_image.width, "height": view_image.height,
                }, np.ascontiguousarray(np.asarray(view_image)[:, :, ::-1])

    def _boxes(self, raw) -> list[dict]:
        if self.name == "rapidocr":
            if raw.txts is None:
                return []
            if raw.boxes is None or raw.scores is None or not (len(raw.boxes) == len(raw.txts) == len(raw.scores)):
                raise ValueError("incomplete RapidOCR box/text/confidence output")
            raw = zip(raw.boxes, raw.txts, raw.scores)
        result = []
        for points, text, confidence in raw:
            value = float(confidence)
            polygon = np.asarray(points, dtype=float)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("OCR confidence must be finite and between 0 and 1")
            if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
                raise ValueError("OCR box must contain four finite x/y points")
            result.append({"points": polygon.tolist(), "text": str(text), "confidence": value})
        return result

    def read(self, path: Path) -> str:
        self.last_result = None
        path = Path(path)
        try:
            image = load_rgb(path)
        except Exception as exc:
            raise ValueError(f"Cannot read image for {self.name}: {exc}") from exc
        self._ensure_reader()
        views, strong_views = [], defaultdict(list)
        for view, array in self._views(image):
            started = time.perf_counter()
            try:
                if self._raw_reader is not None:
                    raw = self._raw_reader(array)
                elif self.name == "easyocr":
                    source = str(path) if view["id"] == "whole_r0" else array
                    raw = self._reader.readtext(source, detail=1)
                else:
                    raw = self._reader(array)
                view["boxes"] = self._boxes(raw)
            except Exception as exc:
                raise RuntimeError(f"{self.name} failed on {view['id']}: {exc}") from exc
            view["ms"] = (time.perf_counter() - started) * 1000
            retained = [b for b in view["boxes"] if b["confidence"] >= self.metadata["text_min_confidence"]]
            view["text"] = " ".join(b["text"] for b in retained)
            hits = identifier.rank(view["text"], self.parts)
            strong = [part for part, score, _ in hits if score >= identifier.FOLDED]
            for part in strong:
                strong_views[part].append(view["id"])
            view["identifier_hits"] = [{"part_id": p, "score": float(s), "alias": a} for p, s, a in hits]
            view["selection_score"] = [
                int(len(strong) == 1), float(hits[0][1]) if hits else 0.0,
                statistics.fmean(b["confidence"] for b in retained) if retained else 0.0,
            ]
            views.append(view)
        selected = max(views, key=lambda view: tuple(view["selection_score"]))
        self._update_model_metadata()
        self.last_result = {
            "text": selected["text"], "selected_view": selected["id"], "views": views,
            "conflicts": [{"part_id": part, "views": ids} for part, ids in sorted(strong_views.items())]
                         if len(strong_views) > 1 else [],
        }
        return selected["text"]
