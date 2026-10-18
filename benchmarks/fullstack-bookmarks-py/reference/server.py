"""Reference implementation of the fullstack-bookmarks-py benchmark (standard library only)."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", "data"))
FILE = DATA / "bookmarks.json"


def load():
    return json.loads(FILE.read_text()) if FILE.exists() else {"next": 1, "items": []}


def store(db):
    DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(db))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=None, kind="application/json"):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/app.js"):
            name = "app.js" if self.path == "/app.js" else "index.html"
            kind = "text/javascript" if name.endswith(".js") else "text/html"
            return self._send(200, (HERE / "public" / name).read_bytes(), kind)
        if self.path == "/api/bookmarks":
            return self._send(200, list(reversed(load()["items"])))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/bookmarks":
            return self._send(404, {"error": "not found"})
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            b = json.loads(raw or b"{}")
        except ValueError:
            b = {}
        title, url = str(b.get("title") or "").strip(), str(b.get("url") or "")
        if not title or not re.match(r"^https?://", url):
            return self._send(422, {"error": "invalid"})
        db = load()
        item = {"id": db["next"], "title": title, "url": url, "tag": str(b.get("tag") or "").strip()}
        db["next"] += 1
        db["items"].append(item)
        store(db)
        self._send(201, item)

    def do_DELETE(self):
        found = re.match(r"^/api/bookmarks/(\d+)$", self.path)
        if not found:
            return self._send(404, {"error": "not found"})
        db = load()
        kept = [i for i in db["items"] if i["id"] != int(found.group(1))]
        if len(kept) == len(db["items"]):
            return self._send(404, {"error": "not found"})
        db["items"] = kept
        store(db)
        self._send(204)


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "3000"))), Handler).serve_forever()
