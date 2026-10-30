import csv
import json

import pytest

from partsid import make_labels
from partsid.make_labels import MAX_QUERIES, split


def row(pageid, group):
    return {"pageid": str(pageid), "group": group}


def test_reference_is_lowest_pageid_and_its_session_never_becomes_a_query():
    ref, queries, unused = split([row(30, "g2"), row(10, "g1"), row(20, "g1"), row(40, "g3")])
    assert ref["pageid"] == "10"
    assert [q["pageid"] for q in queries] == ["30", "40"]
    assert [u["pageid"] for u in unused] == ["20"]


def test_page_ids_sort_as_numbers_not_strings():
    # Real page ids run from 5 to 9 digits; as strings "10" < "9".
    ref, queries, _ = split([row(10, "g2"), row(9, "g1"), row(100, "g3")])
    assert ref["pageid"] == "9"
    assert [q["pageid"] for q in queries] == ["10", "100"]


def test_one_query_per_session_and_at_most_max_queries():
    rows = [row(1, "a")] + [row(i, "b") for i in (2, 3)] + [row(i, f"s{i}") for i in range(4, 10)]
    _, queries, _ = split(rows)
    assert [q["pageid"] for q in queries] == ["2", "4", "5", "6", "7", "8", "9"][:MAX_QUERIES]
    assert len({q["group"] for q in queries}) == len(queries)


def test_single_session_part_has_no_queries():
    _, queries, unused = split([row(5, "g1"), row(6, "g1")])
    assert queries == [] and len(unused) == 1


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _dataset(tmp_path, curation_extra=(), manifest_skip=()):
    parts = [{"id": "A", "aliases": ["AB123"]}, {"id": "B", "aliases": ["CD456"]}]
    (tmp_path / "parts.json").write_text(json.dumps(parts), encoding="utf-8")
    files = [("A", 9), ("A", 10), ("A", 11), ("B", 5), ("B", 12), ("A", 77), ("B", 77)]
    manifest = [{"part_id": p, "file": f"images/raw/{p}/{i}.jpg", "pageid": str(i), "license": "CC0",
                 "artist": "x", "page_url": "u", "stored_width": "960", "stored_height": "720"}
                for p, i in files if (p, i) not in manifest_skip]
    _write_csv(tmp_path / "manifest.csv", manifest)
    cur = [("A", 9, "g1", "AB123"), ("A", 10, "g2", "ZZ999"), ("A", 11, "g3", "AB123"),
           ("B", 5, "g1", "CD456"), ("B", 12, "g2", "CD456"), ("A", 77, "g4", "AB123"), ("B", 77, "g3", "CD456"),
           *curation_extra]
    curation = [{"part_id": p, "pageid": str(i), "keep": "y", "marking_legible": "y", "marking": mk,
                 "group": g, "judged_size": "960x720"} for p, i, g, mk in cur]
    _write_csv(tmp_path / "curation.csv", curation)


def _labels(tmp_path):
    with open(tmp_path / "labels.csv", encoding="utf-8") as f:
        return {(r["part_id"], r["pageid"]): r for r in csv.DictReader(f)}


def test_main_splits_excludes_multi_part_files_and_flags_catalog_gaps(tmp_path, monkeypatch, capsys):
    _dataset(tmp_path)
    monkeypatch.setattr(make_labels, "DATA", tmp_path)
    make_labels.main()
    labels = _labels(tmp_path)
    assert labels[("A", "9")]["split"] == "catalog"
    assert [k for k, r in labels.items() if r["split"] == "query" and k[0] == "A"] == [("A", "10"), ("A", "11")]
    assert ("A", "77") not in labels and ("B", "77") not in labels  # filed under two parts
    assert labels[("A", "10")]["marking_in_catalog"] == "n"  # "ZZ999" is no catalog part number
    assert labels[("A", "11")]["marking_in_catalog"] == "y"
    assert "ZZ999" in capsys.readouterr().out


def test_main_stops_when_a_kept_photo_is_missing_from_the_manifest(tmp_path, monkeypatch):
    _dataset(tmp_path, manifest_skip={("A", 9)})
    monkeypatch.setattr(make_labels, "DATA", tmp_path)
    with pytest.raises(SystemExit):
        make_labels.main()
    assert not (tmp_path / "labels.csv").exists()


def test_main_warns_when_a_file_is_not_the_size_that_was_judged(tmp_path, monkeypatch, capsys):
    _dataset(tmp_path)
    with open(tmp_path / "curation.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[1]["judged_size"] = "500x375"  # A/10 was labelled on a smaller rendition
    _write_csv(tmp_path / "curation.csv", rows)
    monkeypatch.setattr(make_labels, "DATA", tmp_path)
    make_labels.main()
    out = capsys.readouterr().out
    assert "WARNING" in out and "A/10 (kept) judged at 500x375, stored 960x720" in out


def test_main_checks_the_size_of_dropped_photos_too(tmp_path, monkeypatch, capsys):
    # A dropped photo may be dropped only because it was too small to judge.
    _dataset(tmp_path, curation_extra=[("B", 30, "-", "")])
    with open(tmp_path / "manifest.csv", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    manifest.append({**manifest[0], "part_id": "B", "pageid": "30", "file": "images/raw/B/30.jpg"})
    _write_csv(tmp_path / "manifest.csv", manifest)
    with open(tmp_path / "curation.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[-1].update(keep="n", judged_size="330x248")
    _write_csv(tmp_path / "curation.csv", rows)
    monkeypatch.setattr(make_labels, "DATA", tmp_path)
    make_labels.main()
    assert "B/30 (dropped) judged at 330x248, stored 960x720" in capsys.readouterr().out


def test_main_stops_when_a_curation_row_has_no_judged_size(tmp_path, monkeypatch):
    _dataset(tmp_path)
    with open(tmp_path / "curation.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[3]["judged_size"] = ""
    _write_csv(tmp_path / "curation.csv", rows)
    monkeypatch.setattr(make_labels, "DATA", tmp_path)
    with pytest.raises(SystemExit, match="judged_size"):
        make_labels.main()
    assert not (tmp_path / "labels.csv").exists()
