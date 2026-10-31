import io
import json

import pytest
from PIL import Image

from partsid.web import dataset_path, decode_upload, web_payload


def test_image_serving_rejects_paths_outside_the_dataset(tmp_path):
    data = tmp_path / "data"
    allowed = {"images/raw/A/1.jpg"}
    path = data / "images/raw/A/1.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"test")
    assert dataset_path("images/raw/A/1.jpg", data, allowed) == path
    for bad in ("../secret", "/etc/passwd", "images/raw/A/../../secret", "images/raw/A/2.jpg"):
        with pytest.raises(ValueError):
            dataset_path(bad, data, allowed)


def test_upload_validates_actual_image_bytes_and_size():
    import base64
    image = io.BytesIO()
    Image.new("RGB", (20, 15), "red").save(image, format="PNG")
    encoded = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
    decoded = decode_upload(encoded)
    assert decoded.size == (20, 15)
    for bad in ("not an image", "data:image/png;base64,abc", "data:image/png;base64,dGVzdA=="):
        with pytest.raises(ValueError):
            decode_upload(bad)


def test_web_data_joins_review_by_file_without_hiding_partial_runs(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "parts.json").write_text('[{"id":"A","name":"Part A"}]')
    (data / "labels.csv").write_text('file,part_id,split\nimages/raw/A/ref.jpg,A,catalog\nimages/raw/A/q.jpg,A,query\n')
    (data / "reviews").mkdir()
    (data / "reviews/error_review_2026-10-30.json").write_text(json.dumps({"reviews": [{"image_path": "data/images/raw/A/q.jpg", "observed_text": "A123"}]}))
    out = tmp_path / "results/experiments"
    out.mkdir(parents=True)
    (out / "partial.json").write_text(json.dumps({"name": "partial", "status": "running", "channel": "fused", "config": {}, "summary": {"n": 1}, "records": [{"file": "images/raw/A/q.jpg", "gt": "A", "rankings": {"fused": ["A"]}}]}))
    result = web_payload(tmp_path)
    assert result["samples"][0]["review"]["observed_text"] == "A123"
    assert result["runs"][0]["status"] == "running"
    assert result["catalog"]["A"]["catalog_file"] == "images/raw/A/ref.jpg"


def test_empty_sql_result_counts_as_a_regression_against_correct_baseline(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "parts.json").write_text('[{"id":"A","name":"Part A"}]')
    (data / "labels.csv").write_text('file,part_id,split\nref.jpg,A,catalog\nq.jpg,A,query\n')
    out = tmp_path / "results/experiments"
    out.mkdir(parents=True)
    for name, channel, ranking in [("easyocr_whole", "fused", ["A"]), ("sqlite_keywords", "sql", [])]:
        (out / f"{name}.json").write_text(json.dumps({"name": name, "channel": channel, "status": "complete", "config": {},
            "summary": {"n": 1}, "records": [{"file": "q.jpg", "gt": "A", "rankings": {channel: ranking}}]}))
    result = web_payload(tmp_path)
    sql = next(r for r in result["runs"] if r["name"] == "sqlite_keywords")
    assert sql["summary"]["regressions"] == 1


def test_language_module_is_served_as_javascript():
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from partsid.web import Handler

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/i18n.js") as response:
            assert response.headers.get_content_type() == "text/javascript"
            assert len(response.read()) > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
