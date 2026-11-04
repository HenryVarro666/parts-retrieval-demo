"""Retained OCR evidence: tests replace only the external model call."""
import importlib
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

PARTS = [
    {"id": "LM317", "aliases": ["LM317", "LM317T"]},
    {"id": "NE555", "aliases": ["NE555", "555"]},
]
BOX = [[0, 0], [12, 0], [12, 8], [0, 8]]


@pytest.fixture
def adapter():
    def create(*args, **kwargs):
        return importlib.import_module("partsid.evidence_ocr").EvidenceOCR(*args, **kwargs)
    return create


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "unlabelled.png"
    Image.new("RGB", (100, 50), (15, 30, 200)).save(path)
    return path


def test_whole_retains_boxes_and_filters_text_without_losing_low_confidence_evidence(adapter, photo):
    def model(image):
        assert image[0, 0].tolist() == [200, 30, 15]  # raw-array engines expect BGR
        return [(np.array(BOX), "LM317T", np.float32(0.8)), (BOX, "noise", 0.1)]

    ocr = adapter("easyocr", "cpu", PARTS, raw_reader=model)
    assert ocr.read(photo) == "LM317T"
    result = ocr.last_result
    assert result["selected_view"] == "whole_r0"
    assert result["views"][0]["boxes"][1]["text"] == "noise"
    assert result["views"][0]["boxes"][0]["points"] == BOX
    assert result["views"][0]["crop"] == [0, 0, 100, 50]
    assert len(result["views"]) == 1
    json.dumps({"evidence": result, "metadata": ocr.metadata}, allow_nan=False)


def test_empty_results_are_valid_evidence_with_original_view(adapter, photo):
    ocr = adapter("easyocr", "cpu", PARTS, raw_reader=lambda image: [])
    assert ocr.read(photo) == ""
    assert ocr.last_result["selected_view"] == "whole_r0"
    assert ocr.last_result["conflicts"] == []
    assert ocr.last_result["views"][0]["boxes"] == []


def test_multiview_geometry_is_fixed_and_keeps_original_first(adapter, photo):
    ocr = adapter("easyocr", "cpu", PARTS, multiview=True, raw_reader=lambda image: [])
    ocr.read(photo)
    views = ocr.last_result["views"]
    assert [(v["id"], v["rotation"], v["width"], v["height"]) for v in views] == [
        ("whole_r0", 0, 100, 50), ("whole_r90", 90, 50, 100),
        ("whole_r180", 180, 100, 50), ("whole_r270", 270, 50, 100),
        ("center_r0", 0, 84, 42), ("center_r90", 90, 42, 84),
        ("center_r180", 180, 84, 42), ("center_r270", 270, 42, 84),
    ]
    assert views[4]["crop"] == [8, 4, 92, 46]
    assert ocr.last_result["selected_view"] == "whole_r0"
    assert ocr.metadata["catalog_guided_view_selection"] is True
    assert ocr.metadata["confidence_calibrated"] is False


def test_strong_identifier_evidence_beats_high_confidence_garbage(adapter, photo):
    outputs = iter([[(BOX, "garbage", 0.99)]] * 4 + [[(BOX, "LM317T", 0.4)]] + [[]] * 3)
    ocr = adapter("easyocr", "cpu", PARTS, multiview=True, raw_reader=lambda image: next(outputs))
    assert ocr.read(photo) == "LM317T"
    assert ocr.last_result["selected_view"] == "center_r0"
    assert ocr.last_result["conflicts"] == []


def test_different_strong_part_hypotheses_remain_visible_as_conflicts(adapter, photo):
    outputs = iter([[(BOX, "NE555", 0.8)], [(BOX, "LM317T", 0.9)]] + [[]] * 6)
    ocr = adapter("easyocr", "cpu", PARTS, multiview=True, raw_reader=lambda image: next(outputs))
    assert ocr.read(photo) == "LM317T"
    assert {c["part_id"] for c in ocr.last_result["conflicts"]} == {"LM317", "NE555"}
    assert next(c for c in ocr.last_result["conflicts"] if c["part_id"] == "NE555")["views"] == ["whole_r0"]


def test_alternative_views_are_never_concatenated_into_an_invented_identifier(adapter, photo):
    outputs = iter([[(BOX, "LM", 0.9)]] + [[]] * 3 + [[(BOX, "317T", 0.8)]] + [[]] * 3)
    ocr = adapter("easyocr", "cpu", PARTS, multiview=True, raw_reader=lambda image: next(outputs))
    assert ocr.read(photo) == "LM"
    assert ocr.last_result["conflicts"] == []


def test_rapid_output_preserves_numpy_boxes_and_handles_no_text(adapter, photo):
    populated = SimpleNamespace(boxes=np.array([BOX]), txts=("LM317T",), scores=(np.float32(0.8),), elapse=0.01)
    outputs = iter([populated, SimpleNamespace(boxes=None, txts=None, scores=None, elapse=0.0)])
    ocr = adapter("rapidocr", "mps", PARTS, raw_reader=lambda image: next(outputs))
    assert ocr.read(photo) == "LM317T"
    assert ocr.last_result["views"][0]["boxes"][0]["points"] == BOX
    json.dumps(ocr.last_result, allow_nan=False)
    assert ocr.read(photo) == ""
    assert ocr.last_result["views"][0]["boxes"] == []


def test_native_easyocr_original_view_preserves_path_decode_and_is_lazy(adapter, photo, monkeypatch):
    calls = []

    class Reader:
        def __init__(self, *args, **kwargs):
            calls.append("loaded")

        def readtext(self, image, **kwargs):
            assert image == str(photo)
            assert kwargs == {"detail": 1}
            return [(BOX, "LM317T", 0.8)]

    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=Reader))
    ocr = adapter("easyocr", "cpu", PARTS)
    assert calls == []
    assert ocr.read(photo) == "LM317T"
    assert calls == ["loaded"]
    assert "path" in ocr.metadata["input_policy"]


def test_engine_failure_is_explicit_and_never_leaves_previous_evidence(adapter, photo):
    outputs = iter([[(BOX, "LM317T", 0.8)]])
    ocr = adapter("easyocr", "cpu", PARTS, raw_reader=lambda image: next(outputs))
    ocr.read(photo)
    with pytest.raises(RuntimeError, match="easyocr.*whole_r0"):
        ocr.read(photo)
    assert ocr.last_result is None


def test_nonfinite_model_scores_are_rejected(adapter, photo):
    ocr = adapter("easyocr", "cpu", PARTS, raw_reader=lambda image: [(BOX, "LM317T", float("nan"))])
    with pytest.raises(RuntimeError, match="confidence"):
        ocr.read(photo)
    assert ocr.last_result is None
