import copy
import json
from pathlib import Path

import pytest

from partsid.ensemble import decide, estimate_ms, validate_inputs


def sample():
    def ocr(ranking):
        return {"rankings": {"fused": ranking}, "id_hits": [], "evidence": {"conflicts": []}, "ms": {"total": 10}}
    return {"easyocr_whole": ocr(["A", "B", "C"]), "easyocr_views": ocr(["A", "B", "C"]),
            "rapidocr_whole": ocr(["B", "A", "C"]), "rapidocr_views": ocr(["B", "C", "A"]),
            "qwen_vlm_top10": {"rankings": {"fused": ["A", "B", "C"]},
                               "vlm": {"selected_id": "C", "abstained": False, "generation_ms": 100}}}


def test_correlated_votes_and_family_votes_are_counted_differently():
    records = sample()
    records["rapidocr_views"]["rankings"]["fused"] = ["C", "B", "A"]
    records["qwen_vlm_top10"]["vlm"].update(selected_id=None, abstained=True)
    assert decide(records, "ensemble_vote5")["ranking"][0] == "A"
    # One EasyOCR opinion, one RapidOCR opinion: tied, so prefer RapidOCR's C.
    assert decide(records, "ensemble_family_vote")["ranking"][0] == "C"


def test_vlm_abstention_is_not_a_vote_for_the_inherited_baseline_top1():
    records = sample()
    records["qwen_vlm_top10"]["vlm"].update(selected_id=None, abstained=True)
    result = decide(records, "ensemble_family_vote")
    assert result["ranking"][0] == "B"
    assert next(v for v in result["votes"] if v["expert"] == "qwen_vlm_top10")["candidate"] is None


def test_rrf_counts_the_vlm_selection_without_its_inherited_tail():
    records = sample()
    # A and B tie across the two OCR lists; the singleton VLM opinion makes C first.
    records["easyocr_whole"]["rankings"]["fused"] = ["A", "B", "C"]
    records["rapidocr_views"]["rankings"]["fused"] = ["B", "A", "C"]
    assert decide(records, "ensemble_rrf")["ranking"] == ["C", "A", "B"]


def test_strong_gate_skips_vlm_only_on_unique_agreeing_unconflicted_identifier():
    records = sample()
    rapid = records["rapidocr_views"]
    rapid["id_hits"] = [["B", 0.9, "B123"]]
    result = decide(records, "ensemble_strong_gate")
    assert result["ranking"][0] == "B" and result["vlm_called"] is False
    rapid["evidence"]["conflicts"] = [{"part_id": "A"}, {"part_id": "B"}]
    result = decide(records, "ensemble_strong_gate")
    assert result["ranking"][0] == "C" and result["vlm_called"] is True
    rapid["evidence"]["conflicts"] = []
    rapid["id_hits"] = [["A", 1.0, "A123"]]
    assert decide(records, "ensemble_strong_gate")["vlm_called"] is True


def test_gates_fall_back_to_new_ocr_on_invalid_or_uncertain_vlm():
    records = sample()
    records["qwen_vlm_top10"]["vlm"].update(selected_id="OUTSIDE", abstained=False)
    assert decide(records, "ensemble_strong_gate")["ranking"][0] == "B"
    records["qwen_vlm_top10"]["vlm"].update(selected_id="C", abstained=True)
    assert decide(records, "ensemble_disagreement_gate")["ranking"][0] == "B"
    records["easyocr_whole"]["rankings"]["fused"] = ["B", "A", "C"]
    assert decide(records, "ensemble_disagreement_gate")["vlm_called"] is False


def test_decisions_do_not_depend_on_ground_truth_or_review_fields():
    records = sample()
    expected = decide(records, "ensemble_family_vote")
    for record in records.values():
        record.update(gt="SECRET", marking="SECRET", review={"observed_text": "SECRET"})
    assert decide(records, "ensemble_family_vote") == expected


def test_cost_counts_abstaining_generation_and_shared_candidate_pass_once():
    records = sample()
    records["qwen_vlm_top10"]["vlm"].update(selected_id=None, abstained=True)
    decision = decide(records, "ensemble_strong_gate")
    assert estimate_ms(records, "ensemble_strong_gate", decision) == 120
    decision = decide(records, "ensemble_family_vote")
    assert estimate_ms(records, "ensemble_family_vote", decision) == 120
    records["rapidocr_views"]["id_hits"] = [["B", 1.0, "B123"]]
    decision = decide(records, "ensemble_strong_gate")
    assert estimate_ms(records, "ensemble_strong_gate", decision) == 10


def test_input_alignment_rejects_duplicates_missing_queries_and_label_mismatch():
    docs = {name: {"status": "complete", "records": [{"file": "one", "gt": "A", **record}]}
            for name, record in sample().items()}
    assert list(validate_inputs(docs, {"one": "A"})) == ["one"]
    wrong = copy.deepcopy(docs)
    wrong["easyocr_views"]["records"] *= 2
    with pytest.raises(ValueError):
        validate_inputs(wrong, {"one": "A"})
    wrong = copy.deepcopy(docs)
    wrong["easyocr_views"]["records"] = []
    with pytest.raises(ValueError):
        validate_inputs(wrong, {"one": "A"})
    wrong = copy.deepcopy(docs)
    wrong["rapidocr_views"]["records"][0]["gt"] = "B"
    with pytest.raises(ValueError):
        validate_inputs(wrong, {"one": "A"})
