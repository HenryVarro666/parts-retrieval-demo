import csv
import http.client
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from partsid import fetch_commons
from partsid.evaluate import _p, families, paired
from partsid.fetch_commons import merged_manifest
from partsid.images import orientation, upright_rgb


def _row(part, pageid, **extra):
    return {"part_id": part, "pageid": str(pageid), "file": f"images/raw/{part}/{pageid}.jpg", **extra}


def test_merged_manifest_keeps_unfinished_parts_and_drops_removed_ones():
    previous = {("A", "1"): _row("A", 1), ("A", "2"): _row("A", 2), ("B", "3"): _row("B", 3),
                ("GONE", "4"): _row("GONE", 4)}
    rows = [_row("A", 1, image_url="new")]
    merged = merged_manifest(previous, rows, done={"A"}, part_ids={"A", "B"})
    keys = [(r["part_id"], r["pageid"]) for r in merged]
    # B is carried although none of its files exist; GONE left parts.json; A/2 was not re-listed.
    assert keys == [("A", "1"), ("B", "3")]
    assert merged[0]["image_url"] == "new"


def test_from_manifest_rebuild_keeps_rows_whose_download_fails(tmp_path, monkeypatch):
    (tmp_path / "parts.json").write_text(json.dumps([{"id": "A"}]), encoding="utf-8")
    rows = [{"part_id": "A", "file": f"images/raw/A/{i}.jpg", "pageid": str(i), "title": f"File:{i}.jpg",
             "page_url": "p", "license": "CC0", "artist": "x", "width": "2000", "height": "1500",
             "file_url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{i}.jpg",
             "image_url": f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{i}.jpg/960px-{i}.jpg",
             "stored_width": "960", "stored_height": "720"} for i in (1, 2)]
    with open(tmp_path / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fetch_commons.FIELDS)
        w.writeheader()
        w.writerows(rows)
    tried = []

    def throttled(urls, path, *, pause, size=None):
        tried.append((urls, size))
        return None, "HTTP 429"

    monkeypatch.setattr(fetch_commons, "DATA", tmp_path)
    monkeypatch.setattr(fetch_commons, "download", throttled)
    monkeypatch.setattr(fetch_commons.shutil, "which", lambda name: "curl")
    monkeypatch.setattr(sys, "argv", ["fetch_commons", "--from-manifest", "--pause", "0"])
    with pytest.raises(SystemExit) as exit_info:
        fetch_commons.main()
    assert exit_info.value.code == 1
    with open(tmp_path / "manifest.csv", encoding="utf-8") as f:
        after = list(csv.DictReader(f))
    assert [r["pageid"] for r in after] == ["1", "2"]  # nothing dropped; a rerun retries both
    # Only the recorded rendition, at the recorded size: no fallback to today's candidates.
    assert tried == [([r["image_url"]], (960, 720)) for r in rows]


def _fake_curl(size):
    """subprocess.run stand-in for download(): curl "fetches" a JPEG of the given size."""
    def run(cmd, **kwargs):
        Image.new("RGB", size, "gray").save(Path(cmd[cmd.index("-o") + 1]), format="JPEG")
        return subprocess.CompletedProcess(cmd, 0, stdout="200", stderr="")
    return run


def test_download_refuses_a_rendition_of_another_size(tmp_path, monkeypatch):
    path = tmp_path / "1.jpg"
    Image.new("RGB", (330, 330), "red").save(path, format="JPEG")
    before = path.read_bytes()
    monkeypatch.setattr(fetch_commons.subprocess, "run", _fake_curl((960, 960)))
    url, why = fetch_commons.download(["u"], path, pause=0, size=(330, 330))
    assert url is None and "960x960" in why
    assert path.read_bytes() == before and not path.with_name("1.jpg.part").exists()
    assert fetch_commons.download(["u"], path, pause=0, size=(960, 960)) == ("u", "")
    assert fetch_commons._stored_size(path) == (960, 960)


def test_from_manifest_keeps_a_file_with_no_recorded_url_at_the_recorded_size(tmp_path, monkeypatch, capsys):
    (tmp_path / "parts.json").write_text(json.dumps([{"id": "A"}]), encoding="utf-8")
    row = {"part_id": "A", "file": "images/raw/A/1.jpg", "pageid": "1", "title": "File:1.jpg", "page_url": "p",
           "license": "CC0", "artist": "x", "width": "1624", "height": "1296",
           "file_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/1.jpg", "image_url": "",
           "stored_width": "960", "stored_height": "766"}
    with open(tmp_path / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fetch_commons.FIELDS)
        w.writeheader()
        w.writerow(row)
    (tmp_path / "images" / "raw" / "A").mkdir(parents=True)
    Image.new("RGB", (960, 766)).save(tmp_path / "images" / "raw" / "A" / "1.jpg", format="JPEG")

    def no_download(*args, **kwargs):
        raise AssertionError("the local file is the recorded size; nothing should be fetched")

    monkeypatch.setattr(fetch_commons, "DATA", tmp_path)
    monkeypatch.setattr(fetch_commons, "download", no_download)
    monkeypatch.setattr(fetch_commons.shutil, "which", lambda name: "curl")
    monkeypatch.setattr(sys, "argv", ["fetch_commons", "--from-manifest", "--pause", "0"])
    fetch_commons.main()  # exits normally: nothing missing, nothing stale
    with open(tmp_path / "manifest.csv", encoding="utf-8") as f:
        (after,) = csv.DictReader(f)
    assert after["image_url"] == "" and (after["stored_width"], after["stored_height"]) == ("960", "766")


def test_a_truncated_file_has_no_stored_size(tmp_path):
    path = tmp_path / "t.jpg"
    Image.effect_noise((256, 256), 64).convert("RGB").save(path, format="JPEG")
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])  # opens fine; fails only when decoded
    assert fetch_commons._stored_size(path) is None


def test_listing_keeps_the_current_upload_of_a_repeated_page(monkeypatch):
    # A one-file category: the API repeats the page with the file's older upload.
    def page(url, width):
        return {"pageid": 7, "title": "File:S1.jpg", "imageinfo": [
            {"mime": "image/jpeg", "url": url, "width": width, "height": 100, "descriptionurl": "d", "extmetadata": {}}]}
    current = page("https://upload.wikimedia.org/wikipedia/commons/a/ab/S1.jpg", 2400)
    older = page("https://upload.wikimedia.org/wikipedia/commons/archive/a/ab/20120301000000%21S1.jpg", 1024)
    monkeypatch.setattr(fetch_commons, "_category_pages", lambda category: [current, older])
    (photo,) = fetch_commons.list_photos(["Some category"])
    assert photo["width"] == 2400 and "/archive/" not in photo["file_url"]


def test_api_requests_retry_a_dropped_connection(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"")
        if len(calls) == 2:
            raise ConnectionResetError("reset by peer")
        return Response()

    monkeypatch.setattr(fetch_commons.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch_commons.time, "sleep", lambda seconds: None)
    assert fetch_commons._get("https://commons.example/api", pause=0) == b"{}"
    assert len(calls) == 3


@pytest.mark.parametrize("value", [0, 9, "6", (6,), 6.0])
def test_an_orientation_that_is_not_1_to_8_is_ignored(value):
    im = Image.new("RGB", (4, 2))
    im.getexif()[0x0112] = value
    assert orientation(im) == -1
    assert upright_rgb(im).size == (4, 2)  # left as it is, no crash


def test_orientation_6_turns_the_image_upright():
    im = Image.new("RGB", (4, 2))
    im.getexif()[0x0112] = 6
    assert orientation(im) == 6 and upright_rgb(im).size == (2, 4)


def _result(gt, **ranks):
    return {"gt": gt, "ranks": {c: ranks.get(c) for c in ("fused", "image")},
            "rankings": {"fused": [], "image": []}}


def test_paired_counts_each_part_once():
    # Part P: fused wins on 3 queries. Part Q: image wins on 1. Per query 3-1, per part 1-1.
    rs = [_result("P", fused=1, image=2) for _ in range(3)] + [_result("Q", fused=2, image=1)]
    p = paired(rs, "fused", "image")
    assert (p["wins"], p["losses"], p["part_wins"], p["part_losses"]) == (3, 1, 1, 1)
    assert p["p_sign_test_parts"] == 1.0


def test_families_count_wrong_answers_inside_the_family():
    parts = [{"id": "X1", "family": "X"}, {"id": "X2", "family": "X"}, {"id": "Y", "family": "Y"}]
    r1 = {"gt": "X1", "ranks": {"image": 2, "fused": 1}, "rankings": {"image": ["X2", "X1"], "fused": ["X1"]}}
    r2 = {"gt": "X2", "ranks": {"image": 3, "fused": 2}, "rankings": {"image": ["Y", "X1", "X2"], "fused": ["X1", "X2"]}}
    (fam,) = families([r1, r2], parts)
    assert fam["n"] == 2 and fam["image_top1"] == 0 and fam["fused_top1"] == 1
    assert fam["image_wrong_in_family"] == 1  # r1 went to X2; r2 went to Y, outside the family
    assert fam["fused_wrong_in_family"] == 1


def test_small_p_values_are_not_printed_as_zero():
    assert _p(2 / 2 ** 14) == "<0.001"
    assert _p(0.0039) == "0.004"
    assert _p(0.51) == "0.51"
