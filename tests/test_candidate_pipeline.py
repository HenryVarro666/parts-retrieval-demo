
from partsid.candidate_pipeline import apply_visual, candidate_prompt, merge_candidates, shape_rerank


def test_pool_retains_strong_sql_and_marks_supplement_without_fake_sql_hits():
    sql = [{"part_id": "A"}, {"part_id": "B"}]
    images = ["C", "A", "D", "E", "F", "G", "H", "I", "J", "K"]
    pool = merge_candidates(sql, images, ["B"], k=10)
    assert pool[0]["part_id"] == "B"
    assert len(pool) == 10 and len({p["part_id"] for p in pool}) == 10
    assert next(p for p in pool if p["part_id"] == "C")["origins"] == ["appearance"]
    assert set(next(p for p in pool if p["part_id"] == "A")["origins"]) == {"sqlite", "appearance"}


def test_empty_sql_is_explicitly_visual_supplement():
    pool = merge_candidates([], ["C", "B", "A"], [], k=2)
    assert [p["part_id"] for p in pool] == ["C", "B"]
    assert all(p["origins"] == ["appearance"] for p in pool)


def test_shape_preserves_strong_aliases_and_does_not_penalize_unknown_shapes():
    assert shape_rerank(["A", "B", "C"], ["A"], {"A": 0.01, "B": 1.0, "C": None})[0] == "A"
    assert shape_rerank(["A", "B", "C"], [], {"A": None, "B": None, "C": None}) == ["A", "B", "C"]


def record():
    return {"rankings": {"sql": ["A"], "hybrid": ["A", "B"], "shape": ["A", "B"]},
            "retrieval": {"strong_ids": ["A"], "candidate_ids": ["A", "B"]}, "evidence": {"conflicts": []}}


def test_visual_is_pool_constrained_and_gate_preserves_unconflicted_strong_alias():
    before = record()
    result = apply_visual(before, {"selected_id": "B", "abstained": False, "observed_text": "B123", "reason": "pixels"})
    assert result["rankings"]["reranked"] == ["B", "A"]
    assert result["rankings"]["gated"] == ["A", "B"]
    assert result["decision"]["used_vlm"] is False
    assert "reranked" not in before["rankings"]
    before["evidence"]["conflicts"] = [{"part_id": "A"}, {"part_id": "B"}]
    assert apply_visual(before, result["vlm"])["rankings"]["gated"] == ["B", "A"]
    invalid = apply_visual(before, {"selected_id": "OUTSIDE", "abstained": False})
    assert invalid["rankings"]["reranked"] == ["A", "B"]
    assert invalid["vlm"]["abstained"] is True


def test_prompt_has_public_candidates_and_heuristic_shape_but_no_labels():
    candidates = [{"id": "A", "name": "Part", "aliases": ["A123"], "description": "IC", "gt": "SECRET", "file": "SECRET", "marking": "SECRET"}]
    prompt = candidate_prompt(candidates, {"available": True, "features": {"elongation": 2}}, {"A": 0.8})
    assert "A123" in prompt and "elongation" in prompt and "heuristic" in prompt
    assert "SECRET" not in prompt
