import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

from scraper import cli, server


@pytest.fixture
def live_server(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    (tmp_path / "data" / "latest.json").write_text(
        json.dumps({"meta": {"run_id": "r1"}, "products": []}), encoding="utf-8")

    httpd = HTTPServer(("127.0.0.1", 0), server.make_handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def post(url, data=b""):
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_serves_dashboard_api_and_404s(live_server):
    status, body = get(f"{live_server}/")
    assert status == 200 and "dashboard" in body

    status, body = get(f"{live_server}/api/latest")
    assert status == 200
    assert json.loads(body)["meta"]["run_id"] == "r1"

    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{live_server}/nope.txt")
    assert exc.value.code == 404

    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{live_server}/nope")
    assert exc.value.code == 404


def test_directory_traversal_is_blocked(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{live_server}/../../etc/passwd")
    assert exc.value.code in (400, 403, 404)


def test_refresh_generic_failure_reports_history_not_saved(live_server, monkeypatch):
    def boom(web_dir=None):
        raise RuntimeError("network is down")

    monkeypatch.setattr(cli, "run", boom)

    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{live_server}/api/refresh")
    assert exc.value.code == 500
    payload = json.loads(exc.value.read().decode("utf-8"))
    assert payload["history_saved"] is False
    assert "network is down" in payload["error"]


def test_refresh_run_outputs_failed_reports_history_saved(live_server, monkeypatch):
    def boom(web_dir=None):
        raise cli.RunOutputsFailed("report.write_latest", ValueError("disk full"))

    monkeypatch.setattr(cli, "run", boom)

    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{live_server}/api/refresh")
    assert exc.value.code == 500
    payload = json.loads(exc.value.read().decode("utf-8"))
    assert payload["history_saved"] is True
    assert "price history was saved" in payload["error"]
