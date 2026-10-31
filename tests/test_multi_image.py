import copy
import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from partsid import multi_image as multi


def evidence(sql, appearance, strong=(), shapes=None):
    ids = list(dict.fromkeys(sql + appearance))[:10]
    return {"ocr_text": " ".join(sql), "evidence": {"views": [], "conflicts": []},
            "retrieval": {"candidates": [{"part_id": p, "matches": [{"term": p, "field": "alias", "kind": "exact_alias"}]} for p in sql],
                          "strong_ids": list(strong), "keywords": [], "candidate_ids": ids,
                          "pool": [{"part_id": p, "origins": (["sqlite"] if p in sql else []) + (["appearance"] if p in appearance else [])} for p in ids]},
            "rankings": {"sql": sql, "image": appearance, "hybrid": ids, "shape": ids, "fused": ids},
            "shape": {"query": {"available": bool(shapes), "features": {}}, "reference_scores": shapes or {}, "ranked_ids": ids},
            "id_hits": [], "ms": {"ocr": 1, "image": 2, "shape": 1, "total": 4}}


def test_complementary_sql_evidence_survives_visual_pool_and_retains_photo_receipts():
    before = [evidence([], ["B", "C", "A"]), evidence(["A"], ["C", "A", "B"], ["A"]), evidence(["A"], ["B", "A", "C"], ["A"])]
    original = copy.deepcopy(before)
    result = multi.fuse_records(before, [0, 1, 2])
    assert result["rankings"]["fused"][0] == "A"
    assert result["fusion"]["support"]["A"]["strong_groups"] == [1, 2]
    assert [m["photo_index"] for m in result["retrieval"]["candidates"][0]["matches"]] == [1, 2]
    assert multi.can_accept_group(result)
    assert before == original


def test_cross_photo_strong_conflict_blocks_gate_and_retains_both_models():
    result = multi.fuse_records([evidence(["A"], ["A", "B"], ["A"]), evidence(["B"], ["B", "A"], ["B"])], [0, 1])
    assert set(result["retrieval"]["candidate_ids"]) == {"A", "B"}
    assert not multi.can_accept_group(result)
    assert result["evidence"]["conflicts"][-1]["kind"] == "cross_photo_strong_conflict"


def test_duplicate_and_near_duplicate_votes_cannot_create_consensus():
    a, b = evidence(["A"], ["A", "B"], ["A"]), evidence(["B"], ["B", "A"], ["B"])
    pair = multi.fuse_records([a, b], [0, 1])
    triplet = multi.fuse_records([a, a, b], [0, 0, 1])
    assert triplet["rankings"] == pair["rankings"]
    assert triplet["fusion"]["support"]["A"]["score"] == pytest.approx(pair["fusion"]["support"]["A"]["score"])
    same_group = multi.fuse_records([a, a, a], [0, 0, 0])
    assert same_group["rankings"]["shape"] == a["rankings"]["shape"]
    assert not multi.can_accept_group(same_group)


def test_unknown_shapes_add_no_evidence_and_candidate_limit_is_enforced():
    rows = [evidence([f"S{i}"], [f"P{j}" for j in range(15)], [f"S{i}"]) for i in range(3)]
    result = multi.fuse_records(rows, [0, 1, 2])
    assert len(result["retrieval"]["candidate_ids"]) == 10
    assert all(f"S{i}" in result["retrieval"]["candidate_ids"] for i in range(3))
    assert all(v is None for v in result["shape"]["reference_scores"].values())


def photos(tmp_path):
    paths = []
    for i in range(3):
        image = Image.new("RGB", (80, 60), "white")
        ImageDraw.Draw(image).rectangle((5 + i * 20, 10, 20 + i * 20, 45), fill="black")
        path = tmp_path / f"{i}.png"
        image.save(path)
        paths.append(path)
    return paths


def test_pixel_duplicates_skip_extraction_but_paired_baseline_is_independent(tmp_path):
    path = photos(tmp_path)[0]
    class Pipeline:
        def __init__(self): self.calls = []
        def run(self, p):
            self.calls.append(Path(p))
            return evidence(["A"], ["B", "A"], ["A"])
    pipeline = Pipeline()
    result = multi.compare_paths(pipeline, [path, path, path])
    assert pipeline.calls == [path, path]
    assert result["record"]["fusion"]["independent_groups"] == 1
    assert [p["duplicate_of"] for p in result["record"]["photos"]] == [None, 0, 0]
    assert result["comparison"]["single"]["top3"] == result["comparison"]["multi"]["top3"]
    assert result["comparison"]["multi"]["elapsed_ms"] > 0


def test_three_distinct_images_are_extracted_independently_and_all_visual_pixels_hashed(tmp_path):
    paths = photos(tmp_path)
    signatures = [multi.image_signature(p) for p in paths]
    assert multi.correlation_groups(signatures) == [0, 1, 2]
    class Pipeline:
        root = tmp_path
        parts = {p: {"id": p, "aliases": [p], "gt": "NEVER_PROMPT", "file": "NEVER_PROMPT"} for p in ["A", "B"]}
        reference_paths = {"A": paths[0], "B": paths[1]}
    record = multi.fuse_records([evidence([], ["A", "B"])] * 3, [0, 1, 2])
    record["photos"] = [{"index": i, "group": i, "duplicate_of": None, "record": evidence([], ["A", "B"])} for i in range(3)]
    request = multi.prepare_group_visual(Pipeline(), record, paths, "test")
    assert len(request["images"]) == 4
    assert request["images_sha256"][:3] == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    assert "Image 4" in request["prompt"] and "NEVER_PROMPT" not in request["prompt"]
    paths[2].write_bytes(paths[0].read_bytes())
    changed = multi.prepare_group_visual(Pipeline(), record, paths, "test2")
    assert changed["key"] != request["key"]


def test_visual_outside_pool_abstains_without_discarding_fused_order():
    record = multi.fuse_records([evidence([], ["A", "B"])] * 2, [0, 1])
    result = multi.apply_group_visual(record, {"selected_id": "OUTSIDE", "abstained": False})
    assert result["vlm"]["abstained"]
    assert result["rankings"]["gated"] == record["rankings"]["shape"]


def test_similar_compressed_photos_share_one_vote_group(tmp_path):
    first = photos(tmp_path)[0]
    second = tmp_path / "compressed.jpg"
    Image.open(first).save(second, quality=92)
    assert multi.correlation_groups([multi.image_signature(p) for p in [first, second]]) == [0, 0]
