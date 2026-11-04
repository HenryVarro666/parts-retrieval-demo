import json

from partsid import rerank


def test_rerank_rejects_an_invented_candidate_and_preserves_baseline():
    result = rerank.validate_response('{"selected_id":"INVENTED","observed_text":"123"}', ["A", "B"])
    assert result["abstained"] is True
    assert rerank.apply_selection(["A", "B"], result) == ["A", "B"]


def test_rerank_moves_only_a_valid_confident_candidate():
    result = rerank.validate_response('```json\n{"selected_id":"B","observed_text":"B123","uncertain":false,"reason":"visible B123"}\n```', ["A", "B", "C"])
    assert rerank.apply_selection(["A", "B", "C"], result) == ["B", "A", "C"]
    uncertain = rerank.validate_response('{"selected_id":"B","uncertain":true}', ["A", "B"])
    assert rerank.apply_selection(["A", "B"], uncertain) == ["A", "B"]


def test_malformed_or_ambiguous_model_output_abstains():
    for response in ['plain text', '{"selected_id": ["A"]}', '{"selected_id":"A","uncertain":"false"}', '{"selected_id":"A"}{"selected_id":"B"}',
                     '{"selected_id":"A"}', '{"selected_id":"A","uncertain":false,"observed_text":{},"reason":123}']:
        assert rerank.validate_response(response, ["A", "B"])["abstained"]


def test_duplicate_uncertainty_fields_are_ambiguous_and_abstain():
    raw = '{"selected_id":"B","observed_text":"B123","reason":"text","uncertain":true,"uncertain":false}'
    assert rerank.validate_response(raw, ["A", "B"])["abstained"]


def test_prompt_uses_only_public_candidate_fields():
    prompt = rerank.build_prompt([{"id": "B", "name": "Timer", "aliases": ["B123"],
                                   "description": "timer IC", "gt": "SECRET_GT", "marking": "SECRET_LABEL", "file": "SECRET_PATH"}])
    assert "B123" in prompt
    assert "SECRET" not in prompt
    assert "selected_id" in prompt


def test_summary_counts_regressions_and_full_candidate_recall():
    records = [
        {"gt": "B", "rankings": {"fused": ["A", "B"], "reranked": ["B", "A"]}, "ms": {"total": 10}},
        {"gt": "A", "rankings": {"fused": ["A", "B"], "reranked": ["B", "A"]}, "ms": {"total": 30}},
        {"gt": "C", "rankings": {"fused": ["A", "B"], "reranked": ["A", "B"]}, "ms": {"total": 20}},
    ]
    summary = rerank.summarize(records, "reranked", "fused")
    assert summary["top1_k"] == 1
    assert summary["top3_k"] == 2
    assert summary["recall10_k"] == 2
    assert summary["wins"] == summary["regressions"] == 1
    assert summary["n"] == 3
    assert summary["latency_ms"]["p50"] == 20


def test_visual_cache_invalidates_when_reference_pixels_change():
    from partsid import vlm_worker
    config = {"max_pixels": 100, "max_tokens": 200}
    request = {"key": "one", "prompt_sha256": "p", "images_sha256": ["query", "new-reference"]}
    response = {"key": "one", "prompt_sha256": "p", "images_sha256": ["query", "old-reference"], "max_pixels": 100, "max_tokens": 200}
    assert not vlm_worker.cache_matches(response, request, config)
    response["images_sha256"] = ["query", "new-reference"]
    assert vlm_worker.cache_matches(response, request, config)


def test_smoke_run_does_not_overwrite_a_completed_full_run(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from partsid import experiments
    original = tmp_path / "easyocr_whole.json"
    original.write_text('{"status":"complete","marker":"keep"}')
    class Pipe:
        ocr = SimpleNamespace(metadata={}, last_result={})
        def run(self, path):
            return {"rankings": {"fused": ["A"]}, "ms": {"total": 1}}
    monkeypatch.setattr(experiments, "OUT", tmp_path)
    monkeypatch.setattr(experiments, "make_pipeline", lambda *a: (Pipe(), [], [{"file": "a", "part_id": "A"}], {"a": "a"}))
    experiments.run_ocr("easyocr", limit=1)
    assert json.loads(original.read_text())["marker"] == "keep"
    assert json.loads((tmp_path / "easyocr_whole_smoke1.json").read_text())["status"] == "smoke_subset"
