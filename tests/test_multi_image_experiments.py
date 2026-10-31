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


@pytest.mark.parametrize("name", ["paired_retrieval.json", "duplicate_control.json"])
def test_scope_cannot_promote_exploratory_or_duplicate_data_to_confirmed(name):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    doc = json.loads((root / "results/multi_image" / name).read_text())
    doc["scope"] = "confirmed_same_object"
    with pytest.raises(ValueError): exp.validate_saved(doc, root)


def test_three_crops_of_one_source_capture_are_not_three_real_photos(tmp_path):
    from PIL import Image
    path, doc = manifest(tmp_path)
    original = tmp_path / "data/0.png"
    with Image.open(original) as image:
        for i, box in enumerate([[0,0,30,40], [5,0,45,40], [20,0,70,40]]):
            target = tmp_path / f"data/crop-{i}.png"; image.crop(box).save(target)
            doc["groups"][0]["photos"][i] = {"file": target.name, "sha256": sha256(target),
                "source": {"file": original.name, "sha256": sha256(original), "crop": box}}
    doc["groups"][0]["identity_basis"]["status"] = "user_confirmed"
    doc["scope"] = "confirmed_same_object"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="capture"):
        exp.load_manifest(path, tmp_path)


@pytest.mark.parametrize("field", ["capture_id", "original_document_id", "pageid"])
def test_metadata_rejects_same_capture_even_when_pixels_differ(tmp_path, field):
    from PIL import Image
    path, document = manifest(tmp_path)
    for i, photo in enumerate(document["groups"][0]["photos"]):
        original = tmp_path / f"data/source-{i}.png"
        with Image.open(tmp_path / "data" / photo["file"]) as image:
            image.save(original)
            size = image.size
        photo["source"] = {"file": original.name, "sha256": sha256(original),
                           "crop": [0, 0, *size], field: "same-capture"}
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="capture"):
        exp.load_manifest(path, tmp_path)


def test_catalog_capture_id_excluded_even_for_different_pixels(tmp_path):
    from PIL import Image
    path, document = manifest(tmp_path)
    data = tmp_path / "data"
    Image.new("RGB", (13, 19), "blue").save(data / "catalog.png")
    (data / "labels.csv").write_text("file,part_id,split,pageid\ncatalog.png,A,catalog,123\n")
    photo = document["groups"][0]["photos"][0]
    with Image.open(data / photo["file"]) as image:
        image.save(data / "original.png")
        size = image.size
    photo["source"] = {"file": "original.png", "sha256": sha256(data / "original.png"),
                       "crop": [0, 0, *size], "pageid": 123}
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="catalog"):
        exp.load_manifest(path, tmp_path)


def test_each_view_is_measured_independently_and_replay_binds_its_order(tmp_path):
    from tests.test_multi_image import evidence
    path, document = manifest(tmp_path)
    (tmp_path / "data/parts.json").write_text('[{"id":"A"}]')
    (tmp_path / "data/catalog.sqlite").write_bytes(b"test")
    class Pipeline:
        metadata = {"test": True}
        calls = []
        def run(self, p):
            self.calls.append(p.name)
            return evidence(["A"], ["A", "B"], ["A"])
    pipeline = Pipeline()
    doc = exp.evaluate(document["groups"], pipeline, tmp_path, manifest=path, all_single_views=True)
    assert pipeline.calls == ["0.png", "0.png", "1.png", "2.png", "1.png", "2.png"]
    pair = doc["records"][0]
    assert pair["single_photo_records"][0] == pair["baseline_record"]
    assert [r["photos"][0]["file"] for r in pair["single_photo_records"]] == ["0.png", "1.png", "2.png"]
    assert doc["summary"]["all_single"]["n"] == 3
    assert doc["summary"]["objects"] == 1
    doc["records"][0]["single_photo_records"][2]["photos"][0]["file"] = "0.png"
    with pytest.raises(ValueError, match="single"):
        exp.validate_saved(doc, tmp_path)


def test_public_named_run_without_optional_all_single_views_can_be_reported(tmp_path):
    doc = completed(tmp_path)
    directory = tmp_path / "results/multi_image"
    directory.mkdir(parents=True)
    (directory / "public_regular.json").write_text(json.dumps(doc))
    assert exp.report(tmp_path)["runs"][0]["summary"]["single"]["top1_k"] == 1


def test_web_validation_cache_reuses_only_unchanged_result_and_source_bytes(tmp_path, monkeypatch):
    from partsid.web import multi_payload
    from PIL import Image
    import os
    doc = completed(tmp_path)
    directory = tmp_path / "results/multi_image"
    directory.mkdir(parents=True)
    (directory / "custom.json").write_text(json.dumps(doc))
    calls = []
    validate = exp.validate_saved
    def counted(*args):
        calls.append(True)
        return validate(*args)
    monkeypatch.setattr(exp, "validate_saved", counted)
    assert len(multi_payload(tmp_path)) == len(multi_payload(tmp_path)) == 1
    assert len(calls) == 1
    # Preserve mtime to ensure cache validity does not rely on stat timestamps.
    photo = tmp_path / "data/0.png"
    stat = photo.stat()
    Image.new("RGB", (80, 40), "magenta").save(photo)
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert multi_payload(tmp_path) == []


def test_replay_requires_complete_dependency_hash_coverage(tmp_path):
    doc = completed(tmp_path)
    del doc["sources_sha256"]["data/0.png"]
    with pytest.raises(ValueError, match="coverage"):
        exp.validate_saved(doc, tmp_path)


def test_web_cache_detects_a_retargeted_query_symlink(tmp_path):
    from partsid.web import multi_payload
    from tests.test_multi_image import evidence
    path, document = manifest(tmp_path)
    photo = tmp_path / "data/0.png"
    photo.rename(tmp_path / "data/first-target.png")
    photo.symlink_to("first-target.png")
    (tmp_path / "data/parts.json").write_text('[{"id":"A"}]')
    (tmp_path / "data/catalog.sqlite").write_bytes(b"test")
    class Pipeline:
        metadata = {"test": True}
        def run(self, p): return evidence(["A"], ["A", "B"], ["A"])
    doc = exp.evaluate(document["groups"], Pipeline(), tmp_path, manifest=path)
    directory = tmp_path / "results/multi_image"
    directory.mkdir(parents=True)
    (directory / "custom.json").write_text(json.dumps(doc))
    assert len(multi_payload(tmp_path)) == 1
    photo.unlink()
    photo.symlink_to("1.png")
    assert multi_payload(tmp_path) == []
