"""Local dashboard server. Binds 127.0.0.1 only; never exposed."""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import config

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def make_handler(web_dir):
    web_dir = Path(web_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep the console readable

        def _send(self, status, body, content_type="application/json"):
            payload = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _safe_path(self, path):
            candidate = (web_dir / path.lstrip("/")).resolve()
            if not str(candidate).startswith(str(web_dir)):
                return None
            return candidate

        def do_GET(self):
            route = self.path.split("?")[0]
            if route in ("/", "/index.html"):
                return self._send(200, (web_dir / "index.html").read_bytes(),
                                  CONTENT_TYPES[".html"])
            if route == "/api/latest":
                target = web_dir / "data" / "latest.json"
                if not target.exists():
                    return self._send(404, '{"error":"no data yet"}')
                return self._send(200, target.read_bytes())
            if route == "/api/history":
                target = web_dir / "data" / "history.json"
                if not target.exists():
                    return self._send(404, '{"error":"no history yet"}')
                return self._send(200, target.read_bytes())

            target = self._safe_path(route)
            if target is None or not target.is_file():
                return self._send(404, '{"error":"not found"}')
            suffix = target.suffix.lower()
            return self._send(200, target.read_bytes(),
                              CONTENT_TYPES.get(suffix, "application/octet-stream"))

        def do_POST(self):
            if self.path != "/api/refresh":
                return self._send(404, '{"error":"not found"}')
            from .cli import RunOutputsFailed, run
            try:
                meta = run(web_dir=web_dir)
            except RunOutputsFailed as error:
                return self._send(500, json.dumps({
                    "error": str(error),
                    "history_saved": True,
                }))
            except Exception as error:  # noqa: BLE001 - reported to the browser
                return self._send(500, json.dumps({
                    "error": str(error),
                    "history_saved": False,
                }))
            return self._send(200, json.dumps({
                "ok": True,
                "product_count": meta["product_count"],
                "run_id": meta["run_id"],
            }))

    return Handler


def serve(port=8000, open_browser=True, web_dir=None, server_class=HTTPServer):
    web_dir = web_dir or config.WEB_DIR
    httpd = server_class(("127.0.0.1", port), make_handler(web_dir))
    url = f"http://127.0.0.1:{httpd.server_port}"
    print(f"Dashboard: {url}   (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.shutdown()
