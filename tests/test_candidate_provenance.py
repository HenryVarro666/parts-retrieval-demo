import hashlib
import json

import pytest


def fixture(root):
    data = root / "data"
    data.mkdir()
    (data / "parts.json").write_text('[{"id":"A","aliases":["A123"],"makers":[]}]')
    (data / "labels.csv").write_text('file,part_id,split\nref.jpg,A,catalog\nq1.jpg,A,query\nq2.jpg,A,query\n')
    for name in ("ref.jpg", "q1.jpg", "q2.jpg"):
        (data / name).write_bytes(name.encode())
    (data / "catalog.sqlite").write_bytes(b"database")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    refs = hashlib.sha256(json.dumps([("A", "ref.jpg")], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    catalog = hashlib.sha256(json.dumps(json.loads((data / "parts.json").read_text()), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    config = {"labels_sha256": digest(data / "labels.csv"), "database_sha256": digest(data / "catalog.sqlite"),
              "query_image_sha256": {name: digest(data / name) for name in ("q1.jpg", "q2.jpg")},
              "metadata": {"sqlite": {"references_sha256": refs, "catalog_sha256": catalog}, "reference_image_sha256": {"A": digest(data / "ref.jpg")}}}
    rows = [{"file": name, "gt": "A"} for name in ("q1.jpg", "q2.jpg")]
    return {"status": "complete", "records": rows, "config": config}


def test_complete_stage_rejects_partial_duplicate_and_changed_labels(tmp_path):
    from partsid.candidate_experiments import stage_document, validate_rows
    doc = fixture(tmp_path)
    validate_rows(doc["records"], tmp_path)
    for rows in (doc["records"][:1], doc["records"] * 2, [{"file": "q1.jpg", "gt": "B"}, doc["records"][1]]):
        with pytest.raises(ValueError):
            validate_rows(rows, tmp_path)
    with pytest.raises(ValueError):
        stage_document("sqlite_shape", doc["records"][:1], doc["config"], tmp_path, complete=True)
    assert not (tmp_path / "results/experiments/sqlite_shape.json").exists()


@pytest.mark.parametrize("changed", ["q2.jpg", "ref.jpg", "catalog.sqlite", "labels.csv", "parts.json"])
def test_visual_stage_rejects_stale_input_bytes_before_inference(tmp_path, changed):
    from partsid.candidate_experiments import validate_source
    doc = fixture(tmp_path)
    validate_source(doc, tmp_path)
    path = tmp_path / "data" / changed
    if changed == "parts.json":
        parts = json.loads(path.read_text()); parts[0]["aliases"].append("DIFFERENT")
        path.write_text(json.dumps(parts))
    else:
        path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        validate_source(doc, tmp_path)


def test_factory_rejects_stale_reference_manifest_before_model_load(tmp_path, monkeypatch):
    from partsid import embed
    from partsid.candidate_pipeline import make_candidate_pipeline
    from partsid.sqlite_catalog import build_catalog
    data = tmp_path / "data"
    data.mkdir()
    parts = [{"id": "A", "aliases": ["A123"], "makers": []}]
    (data / "parts.json").write_text(json.dumps(parts))
    build_catalog(parts, data / "catalog.sqlite", [{"part_id": "A", "file": "old.jpg"}])
    (data / "labels.csv").write_text('file,part_id,split\nnew.jpg,A,catalog\n')
    def must_not_load(*args, **kwargs):
        raise RuntimeError("Encoder should not be reached for stale references")
    monkeypatch.setattr(embed, "ImageEncoder", must_not_load)
    with pytest.raises(ValueError, match="reference"):
        make_candidate_pipeline(tmp_path, requested_device="cpu")
