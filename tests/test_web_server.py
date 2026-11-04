"""Real loopback server behavior: error mapping, request limits and response hardening."""
import http.client
import json
import logging
import threading
from http.server import ThreadingHTTPServer

import pytest

from partsid import web
from partsid.web import Handler, is_loopback, parse_args


@pytest.fixture
def server():
    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    instance.daemon_threads = True
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


def request(server, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_html_carries_a_content_security_policy_and_scripts_are_same_origin(server):
    status, headers, body = request(server, "GET", "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "object-src 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    assert "Python" not in headers.get("Server", "")
    assert b"<script src=\"/app.js\"" in body
    status, headers, _ = request(server, "GET", "/app.js")
    assert status == 200 and "Content-Security-Policy" not in headers


def test_unknown_paths_and_traversal_attempts_are_rejected(server):
    for path in ("/nope", "/../pyproject.toml", "/web/app.js", "/api/unknown"):
        status, _, body = request(server, "GET", path)
        assert status in (400, 404), path
        assert json.loads(body)["error"]
    status, _, body = request(server, "GET", "/api/image?file=../pyproject.toml")
    assert status == 400 and json.loads(body)["error"] == "Invalid dataset image or request"
    status, _, _ = request(server, "GET", "/api/image?file=images/raw/NE555/28724.jpg&rotation=45")
    assert status == 400


def test_post_limits_content_type_origin_and_length(server):
    json_headers = {"Content-Type": "application/json"}
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}", headers={"Content-Type": "text/plain"})
    assert status == 415
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                           headers={**json_headers, "Origin": "https://evil.example"})
    assert status == 403
    status, _, _ = request(server, "POST", "/api/predict", body=b"[]", headers=json_headers)
    assert status == 400
    status, _, _ = request(server, "POST", "/api/translate", body=b"{" * 70000, headers=json_headers)
    assert status == 413
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                           headers={**json_headers, "Content-Length": "nonsense"})
    assert status == 400
    status, _, _ = request(server, "POST", "/api/other", body=b"{}", headers=json_headers)
    assert status == 404


def test_unexpected_handler_errors_become_500_json_not_dropped_connections(server, monkeypatch, caplog):
    def broken():
        raise KeyError("missing result file")

    monkeypatch.setattr(web, "web_payload", broken)
    with caplog.at_level(logging.ERROR, logger="partsid.web"):
        status, headers, body = request(server, "GET", "/api/data")
    assert status == 500 and headers["Content-Type"].startswith("application/json")
    assert "server log" in json.loads(body)["error"]
    assert any("GET /api/data failed" in record.message for record in caplog.records)


def test_prediction_failures_are_logged_and_reported_generically(server, monkeypatch, caplog):
    monkeypatch.setattr(web, "predict", lambda payload: (_ for _ in ()).throw(RuntimeError("model exploded")))
    with caplog.at_level(logging.ERROR, logger="partsid.web"):
        status, _, body = request(server, "POST", "/api/predict", body=b"{}",
                                  headers={"Content-Type": "application/json"})
    assert status == 500
    assert "model exploded" not in body.decode()
    assert any("Prediction failed" in record.message for record in caplog.records)


def test_handler_drops_idle_clients_instead_of_waiting_forever():
    assert Handler.timeout == web.SOCKET_TIMEOUT_S > 0


def test_cli_defaults_to_loopback_and_validates_port():
    args = parse_args([])
    assert args.host == "127.0.0.1" and args.port == 8765 and args.log_level == "INFO"
    assert parse_args(["--host", "0.0.0.0", "--port", "0"]).host == "0.0.0.0"
    with pytest.raises(SystemExit):
        parse_args(["--port", "70000"])
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("10.0.0.2") and not is_loopback("host")


def test_allowed_image_set_is_cached_until_an_input_changes(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "labels.csv").write_text("file,part_id,split\nimages/raw/A/1.jpg,A,catalog\n")
    (tmp_path / "results/multi_image").mkdir(parents=True)
    calls = []

    def fake_multi_payload(root):
        calls.append(root)
        return [{"records": [{"record": {"photos": [{"file": "multi/x.png"}]}}]}]

    monkeypatch.setattr(web, "multi_payload", fake_multi_payload)
    web._allowed_cache.clear()
    assert "multi/x.png" in web.allowed_images(tmp_path, "unknown.jpg")
    assert "multi/x.png" in web.allowed_images(tmp_path, "other.jpg")
    assert len(calls) == 1, "saved-run validation must not rerun for every unknown filename"
    assert web.allowed_images(tmp_path, "images/raw/A/1.jpg") >= {"images/raw/A/1.jpg"}
    assert len(calls) == 1
    run = tmp_path / "results/multi_image/new.json"
    run.write_text("{}")
    assert "multi/x.png" in web.allowed_images(tmp_path, "unknown.jpg")
    assert len(calls) == 2, "a new or changed saved run invalidates the cache"


def test_requests_with_an_unexpected_host_header_are_refused(server):
    for host in ("evil.example:1", "evil.example", "127.0.0.1.evil.example"):
        status, _, body = request(server, "GET", "/api/data", headers={"Host": host})
        assert status == 421 and "Host" in json.loads(body)["error"], host
        status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                               headers={"Host": host, "Content-Type": "application/json"})
        assert status == 421
    # DNS rebinding: Origin and Host agree on an attacker name that resolves to loopback.
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                           headers={"Host": "evil.example:8765", "Origin": "http://evil.example:8765",
                                    "Content-Type": "application/json"})
    assert status == 421
    status, _, _ = request(server, "GET", "/app.js", headers={"Host": f"localhost:{server.server_port}"})
    assert status == 200
    status, _, _ = request(server, "GET", "/app.js", headers={"Host": f"[::1]:{server.server_port}"})
    assert status == 200


def raw_request(server, text):
    import socket

    with socket.create_connection(("127.0.0.1", server.server_port), timeout=10) as sock:
        sock.sendall(text.encode())
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    return b"".join(chunks)


def test_malformed_targets_and_origins_get_a_response_instead_of_a_dropped_connection(server):
    # http.client refuses to send a bracketed non-IPv6 target, so write the request bytes directly.
    reply = raw_request(server, f"GET http://[abc]/api/data HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\n\r\n")
    assert reply.startswith(b"HTTP/1.0 400"), reply[:80]
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                           headers={"Content-Type": "application/json", "Origin": "http://[::1"})
    assert status in (400, 403)
    status, _, _ = request(server, "POST", "/api/predict", body=b"{}",
                           headers={"Content-Type": "application/json", "Origin": "null"})
    assert status == 403


def test_one_corrupt_results_file_does_not_disable_the_workbench(tmp_path, caplog):
    data = tmp_path / "data"
    data.mkdir()
    (data / "parts.json").write_text('[{"id":"A","name":"Part A"}]')
    (data / "labels.csv").write_text("file,part_id,split\nref.jpg,A,catalog\nq.jpg,A,query\n")
    experiments = tmp_path / "results/experiments"
    experiments.mkdir(parents=True)
    (experiments / "broken.json").write_text('{"name": "broken", "records": [')
    (experiments / "ok.json").write_text(json.dumps({"name": "ok", "channel": "fused", "status": "complete", "config": {},
                                                      "summary": {"n": 1}, "records": [{"file": "q.jpg", "gt": "A", "rankings": {"fused": ["A"]}}]}))
    multi = tmp_path / "results/multi_image"
    multi.mkdir()
    (multi / "report.json").write_text('{"half": ')
    with caplog.at_level(logging.WARNING, logger="partsid.web"):
        payload = web.web_payload(tmp_path)
    assert [run["name"] for run in payload["runs"]] == ["ok"]
    assert payload["multi_image_runs"] == []
    assert any("broken.json" in record.message for record in caplog.records)
    assert any("report.json" in record.message for record in caplog.records)


def test_upload_checks_the_decoded_container_not_only_the_browser_mime_prefix():
    import base64
    import io

    from PIL import Image

    png = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(png, format="PNG")
    encoded = base64.b64encode(png.getvalue()).decode()
    assert web.decode_upload("data:application/octet-stream;base64," + encoded).size == (4, 4)
    assert web.decode_upload("data:;base64," + encoded).size == (4, 4)
    gif = io.BytesIO()
    Image.new("P", (4, 4)).save(gif, format="GIF")
    with pytest.raises(ValueError):
        web.decode_upload("data:image/png;base64," + base64.b64encode(gif.getvalue()).decode())


def test_live_cache_is_bounded_to_the_newest_namespaces(tmp_path):
    import os
    import time

    cache = tmp_path / "data/cache/multi_live"
    for index in range(5):
        folder = cache / f"run-{index}"
        folder.mkdir(parents=True)
        (folder / "requests.json").write_text("{}")
        stamp = time.time() - (5 - index) * 60
        os.utime(folder, (stamp, stamp))
    assert web.prune_live_cache(tmp_path, keep=2) == 3
    assert sorted(entry.name for entry in cache.iterdir()) == ["run-3", "run-4"]
    assert web.prune_live_cache(tmp_path, keep=2) == 0
    assert web.prune_live_cache(tmp_path / "nowhere", keep=2) == 0
