import json

import pytest

from partsid import multi_image_experiments as exp
from partsid.candidate_pipeline import sha256
from tests.test_multi_image import photos


def manifest(tmp_path):
    data = tmp_path / "data"
    data.mkdir(parents=True)
    paths = photos(data)
    (data / "labels.csv").write_text("file,part_id,split\n")
    group = {"object_id": "unit-1", "part_id": "A", "identity_basis": {"status": "visually_supported", "evidence": "same lot and distinctive scratches"},
             "photos": [{"file": p.name, "sha256": sha256(p)} for p in paths]}
    document = {"schema": 1, "scope": "exploratory_same_object", "groups": [group]}
    path = data / "pairs.json"
    path.write_text(json.dumps(document))
    return path, document


def test_manifest_requires_group_evidence_distinct_photos_and_current_pixels(tmp_path):
    path, document = manifest(tmp_path)
    groups = exp.load_manifest(path, tmp_path)
    assert groups[0]["object_id"] == "unit-1"
    for change in ["evidence", "duplicate", "stale", "escape"]:
        broken = json.loads(json.dumps(document))
        group = broken["groups"][0]
        if change == "evidence": group["identity_basis"]["evidence"] = ""
        if change == "duplicate": group["photos"][2] = group["photos"][0]
        if change == "stale": group["photos"][2]["sha256"] = "0" * 64
        if change == "escape": group["photos"][2]["file"] = "../secret.jpg"
        path.write_text(json.dumps(broken))
        with pytest.raises(ValueError): exp.load_manifest(path, tmp_path)


def test_visual_inference_cannot_be_reported_as_confirmed_physical_pair(tmp_path):
    path, document = manifest(tmp_path)
    document["scope"] = "confirmed_same_object"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="confirmed"):
        exp.load_manifest(path, tmp_path)


def test_catalog_photo_is_not_allowed_in_paired_queries(tmp_path):
    path, document = manifest(tmp_path)
    (tmp_path / "data/labels.csv").write_text("file,part_id,split\n0.png,A,catalog\n")
    with pytest.raises(ValueError, match="catalog"):
        exp.load_manifest(path, tmp_path)


def test_paired_summary_counts_gains_and_regressions_without_counting_photos_as_objects():
    def row(pid, before, after):
        return {"object_id": pid, "gt": "A", "comparison": {
            "single": {"top10": before, "elapsed_ms": 10}, "multi": {"top10": after, "elapsed_ms": 30}}}
    summary = exp.summarize_pairs([row("u1", ["B", "A"], ["A", "B"]), row("u2", ["A", "B"], ["B"] )])
    assert summary["objects"] == 2
    assert summary["single"]["top1_k"] == summary["multi"]["top1_k"] == 1
    assert summary["wins"] == summary["regressions"] == 1
    assert summary["multi"]["recall10_k"] == 1


def completed(tmp_path):
    from tests.test_multi_image import evidence
    path, document = manifest(tmp_path)
    (tmp_path / "data/parts.json").write_text('[{"id":"A"}]')
    (tmp_path / "data/catalog.sqlite").write_bytes(b"fixture; no SQL work in this evaluator test")
    class Pipeline:
        metadata = {"test": True}
        def run(self, p): return evidence(["A"], ["A", "B"], ["A"])
    return exp.evaluate(document["groups"], Pipeline(), tmp_path, manifest=path)


def test_replay_rejects_labels_or_photo_order_changed_after_the_run(tmp_path):
    doc = completed(tmp_path)
    doc["records"][0]["gt"] = "B"
    doc["summary"] = exp.summarize_pairs(doc["records"])
    with pytest.raises(ValueError): exp.validate_saved(doc, tmp_path)
    doc = completed(tmp_path / "fresh")
    doc["records"][0]["record"]["photos"][0]["file"] = "2.png"
    with pytest.raises(ValueError): exp.validate_saved(doc, tmp_path / "fresh")


def test_custom_paired_manifest_images_are_available_in_saved_web_replay(tmp_path):
    from partsid.web import allowed_images
    doc = completed(tmp_path)
    directory = tmp_path / "results/multi_image"; directory.mkdir(parents=True)
    (directory / "custom.json").write_text(json.dumps(doc))
    assert {"0.png", "1.png", "2.png"}.issubset(allowed_images(tmp_path))
