import json
from pathlib import Path

import pytest

from partsid.translation import (build_request, parse_translation, valid_entry,
                                 saved_prose, translation_payload, translate_texts)


def test_part_numbers_quoted_markings_and_numbers_survive_translation_exactly():
    source = "The 'LN3055GR R 719' marking matches 2N3055, not 2N3055A; inspect TO-3 at 5 V."
    request = build_request(source, "es")
    assert "2N3055" not in request["masked"]
    raw = json.dumps({"translation": "Texto: " + request["masked"]})
    result = parse_translation(raw, request)
    for value in ("'LN3055GR R 719'", "2N3055", "2N3055A", "TO-3", "5"):
        assert value in result
    assert source == request["source"]


def test_translation_rejects_missing_duplicate_or_invented_placeholders():
    request = build_request("ATMEGA328P-PU has 28 pins.", "zh")
    token = next(iter(request["protected"]))
    for bad in ("型号正确", request["masked"] + token, request["masked"] + " __KEEP_999__"):
        with pytest.raises(ValueError):
            parse_translation(json.dumps({"translation": bad}), request)
    plain = build_request("The marking is unclear.", "zh")
    for token in ("__KEEP_1__", "__KEEP_1000__", "__KEEP_X_1__"):
        with pytest.raises(ValueError):
            parse_translation(json.dumps({"translation": token}), plain)


def test_possessive_apostrophes_do_not_freeze_ordinary_english_clauses():
    request = build_request("I8088's 40-pin DIP form factor. The text 'iP8088-6' is visible.", "zh")
    assert set(request["protected"].values()) == {"I8088", "40-pin", "DIP", "'iP8088-6'"}
    quoted = build_request("The phrase '8-pin DIP package' describes the form.", "es")
    assert set(quoted["protected"].values()) == {"8-pin", "DIP"}
    uncertain = build_request("The fragment N8028? is uncertain, not N80286.", "es")
    assert set(uncertain["protected"].values()) == {"N8028?", "N80286"}


def test_cache_rejects_source_language_model_or_output_drift():
    request = build_request("The NE555N marking is readable.", "es")
    raw = json.dumps({"translation": "Visible: " + request["masked"]})
    from partsid.translation import make_entry
    entry = make_entry(request, raw, 2)
    assert valid_entry(entry)
    for key, value in (("source", "changed"), ("target", "fr"), ("revision", "changed"),
                       ("translation", "2N3055"), ("prompt_sha256", "changed"), ("raw", 123)):
        assert not valid_entry({**entry, key: value}), key


def test_postedit_preserves_the_validated_model_draft_and_edit_provenance():
    from partsid.translation import make_entry
    request = build_request("C8085A-2 is clear enough to read.", "es")
    draft = make_entry(request, json.dumps({"translation": request["masked"]}), 1)
    edited = make_entry(request, json.dumps({"translation": "El modelo __KEEP_000__ es suficientemente claro para leerlo."}), 1, "assistant_postedit")
    assert not valid_entry(edited)
    edited.update(draft=draft, editor="Codex assistant", edit_note="Remove an untranslated English word.")
    assert valid_entry(edited)
    assert not valid_entry({**edited, "draft": {**draft, "source": "Different source"}})
    rejected = {**draft, "raw": '{"translation":"The marking is clear."}', "rejected": True,
                "validation_error": "Translation changed protected markings or identifiers"}
    assert valid_entry({**edited, "draft": rejected})
    assert not valid_entry({**edited, "draft": {**rejected, "raw": 123}})


def test_saved_prose_collects_only_explanations_and_keeps_observations_out(tmp_path):
    review_dir = tmp_path / "data/reviews"; review_dir.mkdir(parents=True)
    (review_dir / "error_review_2026-10-30.json").write_text(json.dumps({"reviews": [{
        "observed_text": "RAW 741P", "observed_part_number": "741P",
        "comparison_note": "型号可见。", "suggested_action": "裁剪主体。"}]}))
    out = tmp_path / "results/experiments"; out.mkdir(parents=True)
    (out / "test.json").write_text(json.dumps({"records": [{"ocr_text": "RAW OCR", "gt": "UA741",
        "vlm": {"observed_text": "RAW MARKING", "reason": "The marking is unclear."}}]}))
    assert set(saved_prose(tmp_path)) == {"型号可见。", "裁剪主体。", "The marking is unclear."}


def test_frozen_translation_replays_without_local_model_and_ignores_stale_entries(tmp_path):
    from partsid.translation import make_entry
    request = build_request("NE555N is visible.", "es")
    entry = make_entry(request, json.dumps({"translation": request["masked"] + " visible"}), 2)
    directory = tmp_path / "data/translations"; directory.mkdir(parents=True)
    (directory / "prose.json").write_text(json.dumps({"entries": [entry, {**entry, "source": "stale"}]}))
    runtime = tmp_path / "data/cache/prose_translations"; runtime.mkdir(parents=True)
    alternative = make_entry(request, json.dumps({"translation": request["masked"] + " runtime"}), 2)
    (runtime / "runtime.json").write_text(json.dumps({"entries": [alternative]}))
    result = translate_texts([request["source"]], "es", tmp_path)
    assert result["translations"][request["source"]]["text"] == entry["translation"]
    assert request["source"] in translation_payload(tmp_path)
    assert "stale" not in translation_payload(tmp_path)


def test_shipped_translation_cache_covers_saved_prose_and_excludes_live_uploads():
    root = Path(__file__).resolve().parent.parent
    document = json.loads((root / "data/translations/prose.json").read_text())
    sources = set(saved_prose(root))
    entries = document["entries"]
    assert {entry["source"] for entry in entries} == sources
    assert len({(entry["source"], entry["target"]) for entry in entries}) == len(sources) * 3
    assert all(valid_entry(entry) for entry in entries)


@pytest.mark.parametrize("texts,target", [(["x"], "fr"), ("text", "es"), (["x"*4001], "zh"), ([12], "en")])
def test_translation_input_is_bounded_before_any_model_load(texts, target, tmp_path):
    with pytest.raises(ValueError):
        translate_texts(texts, target, tmp_path)


def test_http_translation_uses_frozen_text_without_an_ocr_or_vlm_rerun(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from partsid import web
    from partsid.translation import make_entry
    request = build_request("NE555N is visible.", "es")
    entry = make_entry(request, json.dumps({"translation": request["masked"] + " visible"}), 0)
    directory = tmp_path / "data/translations"; directory.mkdir(parents=True)
    (directory / "prose.json").write_text(json.dumps({"entries": [entry]}))
    monkeypatch.setattr(web, "ROOT", tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        body = json.dumps({"texts": [request["source"]], "language": "es"}).encode()
        http = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/translate", data=body,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(http) as response:
            result = json.load(response)
        assert result["translations"][request["source"]]["text"] == entry["translation"]
    finally:
        server.shutdown(); server.server_close(); thread.join()
