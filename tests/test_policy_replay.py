"""PR-034 / PR-035 rule variants and the offline replay that compares them on frozen evidence."""
from pathlib import Path

import pytest

from partsid import identifier, policy_replay
from partsid.candidate_pipeline import neutral_rrf, shape_rerank
from partsid.multi_image import fuse_records

ROOT = Path(__file__).resolve().parents[1]
PARTS = [{"id": "I8086", "aliases": ["8086", "8086-1", "D8086"]}, {"id": "NE555", "aliases": ["NE555", "555"]},
         {"id": "ESP32", "aliases": ["ESP-WROOM-32"]}]


def test_frozen_identifier_behaviour_is_unchanged_by_default():
    assert identifier.rank("LOT 180861", PARTS)[0][:2] == ("I8086", 1.0)
    assert identifier.rank("5 55", PARTS)[0][:2] == ("NE555", 1.0)
    assert identifier.rank("D8086", PARTS)[0][:2] == ("I8086", 1.0)


def test_digit_guard_ignores_lot_numbers_and_digit_joins_but_keeps_real_markings():
    assert identifier.rank("LOT 180861", PARTS, digit_policy="guard") == []
    assert identifier.rank("180861", PARTS, digit_policy="guard") == []
    assert identifier.rank("8086-1", PARTS, digit_policy="guard")[0][:2] == ("I8086", 1.0)
    assert identifier.rank("8086 LOT", PARTS, digit_policy="guard")[0][:2] == ("I8086", 1.0)
    assert identifier.rank("5 55", PARTS, digit_policy="guard") == []
    assert identifier.rank("555", PARTS, digit_policy="guard")[0][:2] == ("NE555", 1.0)
    assert identifier.rank("D8086 LOT 180861", PARTS, digit_policy="guard")[0][:2] == ("I8086", 1.0)
    assert identifier.rank("ESP WROOM 32", PARTS, digit_policy="guard")[0][:2] == ("ESP32", 1.0)
    assert identifier.rank("NE5SS", PARTS, digit_policy="guard")[0][:2] == ("NE555", identifier.FOLDED)
    with pytest.raises(ValueError):
        identifier.rank("x", PARTS, digit_policy="bogus")


def test_frozen_shape_rule_demotes_unknown_and_neutral_rule_does_not():
    ids, scores = ["A", "B", "C"], {"A": None, "B": 0.0001, "C": None}
    assert shape_rerank(ids, [], scores) == ["B", "A", "C"]
    assert shape_rerank(ids, [], scores, policy="neutral") == ["A", "B", "C"]
    assert shape_rerank(["A", "B"], [], {"A": None, "B": 0.0}) == ["B", "A"]
    assert shape_rerank(["A", "B"], [], {"A": None, "B": 0.0}, policy="neutral") == ["A", "B"]
    # Known candidates are still reordered by shape under the neutral rule (an exact two-way
    # swap ties in RRF and keeps retrieval order, so three known candidates are needed).
    assert shape_rerank(["A", "B", "C", "D"], [], {"A": 0.5, "B": 0.9, "C": 0.7, "D": None},
                        policy="neutral") == ["B", "A", "C", "D"]
    assert shape_rerank(["A", "B", "C"], [], {"A": 0.2, "B": 0.9, "C": None}, policy="neutral") == ["A", "B", "C"]
    assert shape_rerank(["A", "B"], ["B"], {"A": 0.9, "B": None}, policy="neutral")[0] == "B"
    assert neutral_rrf(["A", "B"], []) == ["A", "B"]
    with pytest.raises(ValueError):
        shape_rerank(ids, [], scores, policy="other")


def test_neutral_fusion_gives_unknown_shape_the_mean_contribution():
    def record(ids, image, scores):
        return {"retrieval": {"candidate_ids": ids, "candidates": [], "strong_ids": [], "keywords": [], "pool": []},
                "rankings": {"sql": [], "image": image, "shape": ids, "fused": ids}, "shape": {"reference_scores": scores},
                "evidence": {"conflicts": []}}
    # Two distinct photos (identical records are passed through unfused): B has the only
    # reference shape, A leads both appearance rankings.
    a = record(["A", "B", "C"], ["A", "B", "C"], {"A": None, "B": 0.0001, "C": None})
    b = record(["A", "B", "C"], ["A", "C", "B"], {"A": None, "B": 0.0001, "C": None})
    frozen = fuse_records([a, b], [0, 1])["rankings"]["fused"]
    neutral = fuse_records([a, b], [0, 1], shape_policy="neutral")["rankings"]["fused"]
    assert frozen == ["B", "A", "C"] and neutral == ["A", "B", "C"]
    with pytest.raises(ValueError):
        fuse_records([a, b], [0, 1], shape_policy="x")


def test_replay_reproduces_saved_frozen_rankings_and_reports_rule_effects(tmp_path):
    report = policy_replay.run(ROOT, out_dir=tmp_path)
    fidelity = report["single_queries"]["fidelity"]
    assert fidelity["frozen_replay_matches_saved_shape_ranking"] == fidelity["records"] == 44
    assert fidelity["frozen_replay_matches_saved_shape_scores"] == 44
    for mode, result in report["paired_groups"].items():
        assert result["fidelity"]["frozen_replay_matches_saved"] == result["fidelity"]["records"] == 8, mode
    summaries = report["single_queries"]["summaries"]
    assert summaries["frozen"]["gated_reusable"]["top1_k"] == 41  # the published gated projection
    assert summaries["frozen"]["shape"]["top1_k"] == 38
    assert summaries["pr034_neutral_shape"]["shape_ranking_changed"] == summaries["frozen"]["shape_available"] == 10
    assert summaries["pr035_digit_guard"]["conflicts"] == 0 and summaries["frozen"]["conflicts"] == 1
    assert report["new_inference"] is False and report["replay"] is True
    # The committed replay is reproduced exactly from the committed evidence.
    for name in ("comparison.json", "comparison.md"):
        assert (tmp_path / name).read_text() == (ROOT / "results/policy_replay" / name).read_text(), name
    assert (tmp_path / "comparison.md").read_text().startswith("# PR-034 / PR-035")
