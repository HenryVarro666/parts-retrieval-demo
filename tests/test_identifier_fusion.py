import itertools

import pytest

from partsid.fusion import rrf
from partsid.identifier import for_fusion, normalize, rank, score_part, similarity, trigrams

PARTS = [
    {"id": "I8086", "aliases": ["8086", "D8086", "P8086"]},
    {"id": "I8088", "aliases": ["8088", "P8088"]},
    {"id": "NE555", "aliases": ["NE555", "NE555P", "555"]},
    {"id": "ESP8266", "aliases": ["ESP8266", "ESP-12F"]},
]


def test_trigrams_match_pg_trgm_show_trgm():
    # SELECT show_trgm('word') -> {"  w"," wo","ord","rd ","wor"}
    assert trigrams("word") == {"  w", " wo", "wor", "ord", "rd "}


def test_similarity_matches_pg_trgm_docs_example():
    # SELECT similarity('word', 'two words') -> 0.36363637
    assert similarity("word", "two words") == pytest.approx(4 / 11)


def test_normalize_strips_separators_and_micro_sign():
    assert normalize("µA741 ATmega328P-PU") == "UA741ATMEGA328PPU"


def test_alias_inside_token_is_exact_hit():
    assert score_part("INTEL P8086 L4071234", ["8086"]) == (1.0, "8086")


def test_short_alias_needs_whole_token():
    # "555" inside a lot number must not count as the 555 timer
    score, _ = score_part("LOT 15551 ABC", ["555"])
    assert score < 0.35
    assert score_part("NE 555 TI", ["555"])[0] == 1.0


def test_ocr_glyph_swap_scores_below_exact():
    score, alias = score_part("ESP8Z66 E5P-I2F", ["ESP-12F"])
    assert score == 0.9 and alias == "ESP-12F"


def test_split_token_is_rejoined():
    assert score_part("AI-THINKER ESP -12F", ["ESP-12F"])[0] == 1.0


def test_rank_drops_weak_matches_and_orders_best_first():
    ranked = rank("P8088 (C) INTEL '78", PARTS)
    assert [r[0] for r in ranked][0] == "I8088"
    assert all(r[1] >= 0.35 for r in ranked)
    assert "NE555" not in [r[0] for r in ranked]


def test_rrf_sums_reciprocal_ranks_and_skips_abstaining_channel():
    fused = rrf({"identifier": ["A"], "text": [], "image": ["B", "A"]}, k=60)
    scores = dict(fused)
    assert fused[0][0] == "A"
    assert scores["A"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["B"] == pytest.approx(1 / 61)


def test_rrf_respects_top_k():
    fused = dict(rrf({"image": ["A", "B", "C"]}, top_k=2))
    assert "C" not in fused


def test_trigram_fallback_ignores_short_and_all_digit_tokens():
    # "55" vs "555" shares 3 of 4 trigrams; row numbers, years and date codes are not reads
    assert score_part("LOT 5551", ["555"])[0] < 0.35
    assert rank("1 5 10 15 20 25 30 35 40 45 50 55 60", PARTS) == []
    assert rank("(C) INTEL '80", PARTS) == []


def test_fold_needs_a_real_digit_for_all_digit_alias():
    assert score_part("SSS", ["555"])[0] == 0.0
    assert score_part("5S5", ["555"])[0] == 0.9


def test_three_segment_alias_is_rejoined():
    assert score_part("ESP-WROOM-32", ["ESP-WROOM-32"]) == (1.0, "ESP-WROOM-32")


def test_equal_scores_prefer_the_longer_alias():
    parts = [{"id": "LM7805", "aliases": ["LM7805", "7805"]}, {"id": "I8086", "aliases": ["8086", "D8086"]}]
    assert [r[0] for r in rank("D8086 7805", parts)] == ["I8086", "LM7805"]


def test_fusion_gets_only_strong_identifier_hits():
    assert for_fusion([("I8088", 1.0, "8088"), ("I8086", 0.5, "P8086")]) == ["I8088"]
    assert for_fusion([("I8086", 0.5, "P8086"), ("I8085", 0.4, "8085")]) == ["I8086", "I8085"]


def test_rrf_ties_do_not_depend_on_channel_order():
    a = rrf({"text": ["B", "A"], "image": ["A", "B"]})
    b = rrf({"image": ["A", "B"], "text": ["B", "A"]})
    assert [x for x, _ in a] == [x for x, _ in b] == ["A", "B"]


def test_rrf_three_channel_ties_do_not_depend_on_channel_order():
    # X ranks 1, 7, 2 and Y ranks 2, 1, 7: the same score, summed in a different
    # order. Plain float addition gives them totals one ulp apart, which must not decide.
    chans = {"identifier": ["X", "Y"],
             "text": ["Y", "t2", "t3", "t4", "t5", "t6", "X"],
             "image": ["i1", "X", "i3", "i4", "i5", "i6", "Y"]}
    for order in itertools.permutations(chans):
        fused = [x for x, _ in rrf({c: chans[c] for c in order})]
        assert fused[:2] == ["X", "Y"], order  # tie: both best ranks are 1, so the id decides


REAL = [
    {"id": "UA741", "aliases": ["UA741", "LM741", "MC1741", "741CN", "741"]},
    {"id": "LM7805", "aliases": ["LM7805", "L7805", "L7805CV", "MC7805", "UA7805", "7805"]},
    {"id": "LM317", "aliases": ["LM317", "LM317T", "LM317K", "LM317L", "317"]},
    {"id": "I80286", "aliases": ["80286", "R80286", "N80286", "A80286", "286"]},
    {"id": "MC68000", "aliases": ["MC68000", "MC68000P8", "MC68000L8", "MC68HC000", "68000"]},
]


def test_date_code_with_one_misread_glyph_is_not_a_part_number():
    # 741O, 780G and 802I are YYWW date codes with the last digit read as a letter.
    for text in ("741O", "741Q", "780G", "780I", "802I", "802S"):
        assert rank(text, REAL) == [], text


def test_micro_sign_in_read_text_matches_ascii_alias():
    # Catalog aliases and OCR text get the same µ -> U mapping.
    assert rank("µA741C 8833", REAL)[0][:2] == ("UA741", 1.0)


def test_partial_reads_with_a_maker_prefix_still_match():
    assert rank("L317", REAL)[0][0] == "LM317"
    assert rank("MC6804", REAL)[0][0] == "MC68000"
