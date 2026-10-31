"""Behavioral contracts for the real local SQLite candidate store."""
import copy
import hashlib
import importlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest


PARTS = [
    {"id": "NE555", "name": "555 timer IC", "family": "analog",
     "aliases": ["NE555", "NE555N", "555"], "makers": ["Texas Instruments", "Signetics"],
     "description": "Bipolar timer for delays and oscillators, usually 8-pin DIP."},
    {"id": "UA741", "name": "741 operational amplifier", "family": "analog",
     "aliases": ["UA741", "LM741", "741"], "makers": ["Texas Instruments"],
     "description": "General purpose operational amplifier."},
    {"id": "ESP8266", "name": "Wi-Fi module", "family": "wireless",
     "aliases": ["ESP8266", "ESP-12F", "ESP-WROOM-02"], "makers": ["Espressif", "Ai-Thinker"],
     "description": "Wireless microcontroller with a metal shield."},
    {"id": "I8086", "name": "Intel 8086 microprocessor", "family": "x86",
     "aliases": ["8086", "D8086", "P8086"], "makers": ["Intel"],
     "description": "16-bit microprocessor."},
    {"id": "I8088", "name": "Intel 8088 microprocessor", "family": "x86",
     "aliases": ["8088", "D8088", "P8088"], "makers": ["Intel"],
     "description": "Microprocessor with an 8-bit external bus."},
    {"id": "LM317", "name": "Adjustable voltage regulator", "family": "regulators",
     "aliases": ["LM317", "LM317T", "317"], "makers": ["Texas Instruments"],
     "description": "Adjustable positive linear voltage regulator."},
]


@pytest.fixture
def module():
    return importlib.import_module("partsid.sqlite_catalog")


@pytest.fixture
def catalog(module, tmp_path):
    path = tmp_path / "catalog.sqlite"
    module.build_catalog(PARTS, path)
    return module.SQLiteCatalog(path)


def test_build_reopens_the_same_catalog_without_mutating_source(tmp_path):
    module = importlib.import_module("partsid.sqlite_catalog")
    parts = copy.deepcopy(PARTS)
    before = copy.deepcopy(parts)
    path = tmp_path / "catalog.sqlite"
    metadata = module.build_catalog(parts, path, references=[{"part_id": "NE555", "file": "ref.jpg"}])
    expected_sha = hashlib.sha256(json.dumps(PARTS, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert parts == before
    assert metadata["catalog_sha256"] == expected_sha
    assert metadata["part_count"] == 6
    assert metadata["reference_count"] == 1
    assert metadata["sqlite_version"] == sqlite3.sqlite_version
    assert isinstance(metadata["schema_version"], int)
    assert metadata["confidence_calibrated"] is False
    assert module.SQLiteCatalog(path).metadata == metadata
    assert module.SQLiteCatalog(path).search("NE555N")["candidates"][0]["part_id"] == "NE555"


def test_explicit_rebuild_replaces_its_own_database_and_changes_fingerprint(module, tmp_path):
    path = tmp_path / "catalog.sqlite"
    first = module.build_catalog(PARTS, path)
    second = module.build_catalog(PARTS, path)
    assert first == second
    changed = copy.deepcopy(PARTS)
    changed[0]["description"] = "Different public description"
    third = module.build_catalog(changed[1:], path)
    assert third["catalog_sha256"] != first["catalog_sha256"]
    assert third["part_count"] == 5
    assert module.SQLiteCatalog(path).search("NE555N")["strong_ids"] == []


def test_exact_alias_has_a_receipt_and_outranks_weak_description_matches(catalog):
    result = catalog.search("voltage NE555N")
    first = result["candidates"][0]
    assert first["part_id"] == "NE555"
    assert first["tier"] == "exact"
    assert result["strong_ids"] == ["NE555"]
    assert {"term": "NE555N", "field": "aliases", "kind": "exact", "matched_alias": "NE555N"}.items() <= first["matches"][0].items()
    assert next(k for k in result["keywords"] if k["normalized"] == "NE555N")["kind"] == "model"


def test_folded_alias_is_strong_but_below_an_exact_alias(catalog):
    result = catalog.search("E5P-I2F NE555N")
    assert [p["part_id"] for p in result["candidates"][:2]] == ["NE555", "ESP8266"]
    candidate = result["candidates"][1]
    assert candidate["tier"] == "folded"
    assert any(m["matched_alias"] == "ESP-12F" and m["kind"] == "folded" for m in candidate["matches"])
    assert set(result["strong_ids"]) == {"NE555", "ESP8266"}


def test_split_alias_is_recognized_without_requiring_the_noise_term(catalog):
    result = catalog.search("AI-THINKER ESP -12F XQZZ")
    assert result["candidates"][0]["part_id"] == "ESP8266"
    assert result["candidates"][0]["tier"] == "exact"
    assert any(k["normalized"] == "ESP12F" and k["kind"] == "model" for k in result["keywords"])


def test_batch_like_token_is_retained_as_noise_and_does_not_filter_good_alias(catalog):
    result = catalog.search("NE555N 8809VL")
    assert result["strong_ids"] == ["NE555"]
    assert next(k for k in result["keywords"] if k["normalized"] == "8809VL")["kind"] == "noise"
    assert all(m["term"] != "8809VL" for p in result["candidates"] for m in p["matches"])


def test_multiple_useful_keywords_add_evidence_without_duplicate_votes(catalog):
    simple = catalog.search("NE555N")
    supported = catalog.search("NE555N Texas Instruments")
    repeated = catalog.search("NE555N Texas Instruments NE555N TEXAS INSTRUMENTS")
    assert supported["candidates"][0]["score"] > simple["candidates"][0]["score"]
    assert repeated["candidates"] == supported["candidates"]
    assert len([k for k in repeated["keywords"] if k["normalized"] == "NE555N"]) == 1
    assert any(m["field"] == "makers" and m["matched_value"] == "Texas Instruments" for m in supported["candidates"][0]["matches"])


def test_maker_mentions_find_only_that_makers_parts_and_are_never_strong(catalog):
    result = catalog.search("Intel")
    assert {p["part_id"] for p in result["candidates"]} == {"I8086", "I8088"}
    assert all(p["tier"] == "maker" for p in result["candidates"])
    assert result["strong_ids"] == []
    assert result["keywords"][0]["kind"] == "maker"


def test_description_fts_is_a_weak_per_term_fallback(catalog):
    result = catalog.search("adjustable voltage XQZZ")
    assert [p["part_id"] for p in result["candidates"]] == ["LM317"]
    assert result["candidates"][0]["tier"] == "fts"
    assert result["strong_ids"] == []
    assert any(m["field"] == "description" and m["term"] == "voltage" for m in result["candidates"][0]["matches"])


def test_prefixed_partial_read_can_use_trigram_fallback(catalog):
    result = catalog.search("L317")
    assert result["candidates"][0]["part_id"] == "LM317"
    assert result["candidates"][0]["tier"] == "fuzzy"
    assert result["strong_ids"] == []


@pytest.mark.parametrize("text", ["", "   ", "XQZZ VVYX", "55", "5551", "15551", "180861", "741O", "SSS", "8809VL"])
def test_unknown_short_and_batch_reads_do_not_invent_sql_candidates(catalog, text):
    result = catalog.search(text)
    assert result["candidates"] == []
    assert result["strong_ids"] == []


def test_short_numeric_alias_requires_a_whole_token_and_fold_needs_a_real_digit(catalog):
    assert catalog.search("555")["strong_ids"] == ["NE555"]
    assert catalog.search("5S5")["strong_ids"] == ["NE555"]


def test_operator_punctuation_is_only_text_and_cannot_change_database(catalog):
    assert catalog.search("'; DROP TABLE aliases; -- \" OR NEAR(* @@") ["candidates"] == []
    result = catalog.search('"adjustable" OR "*"')
    assert [p["part_id"] for p in result["candidates"]] == ["LM317"]
    assert catalog.search("NE555N")["strong_ids"] == ["NE555"]


def test_box_views_are_never_joined_into_an_invented_alias(catalog):
    separated = [{"text": "ESP", "view_id": "a"}, {"text": "12F", "view_id": "b"}]
    same_view = [{"text": "ESP", "view_id": "a"}, {"text": "12F", "view_id": "a"}]
    assert catalog.search("ESP 12F", boxes=separated)["strong_ids"] == []
    assert catalog.search("ESP 12F", boxes=same_view)["strong_ids"] == ["ESP8266"]


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, "2"])
def test_invalid_limit_is_rejected(catalog, limit):
    with pytest.raises(ValueError, match="limit"):
        catalog.search("Intel", limit=limit)


def test_limit_does_not_change_strong_evidence_outside_returned_top_k(catalog):
    result = catalog.search("NE555N ESP8266", limit=1)
    assert len(result["candidates"]) == 1
    assert set(result["strong_ids"]) == {"NE555", "ESP8266"}


def test_one_catalog_instance_can_be_reused_by_different_threads(catalog):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: catalog.search("ESP -12F"), range(9)))
    assert all(r["strong_ids"] == ["ESP8266"] for r in results)
    json.dumps(results, allow_nan=False)


def test_missing_database_is_not_silently_created(module, tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        module.SQLiteCatalog(path)
    assert not path.exists()


def test_rebuild_refuses_to_overwrite_an_unrelated_file(module, tmp_path):
    path = tmp_path / "foreign.sqlite"
    path.write_bytes(b"unrelated content")
    with pytest.raises(ValueError, match="catalog"):
        module.build_catalog(PARTS, path)
    assert path.read_bytes() == b"unrelated content"
