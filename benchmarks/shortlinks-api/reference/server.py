"""Reference implementation of the shortlinks-api benchmark (standard library only)."""
import json
import os
import re
import secrets
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "data")) / "links.json"
LOCK = threading.Lock()
ALPHABET = string.ascii_letters + string.digits


def load():
    return json.loads(DATA.read_text()) if DATA.exists() else {}


def store(links):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(links))
    tmp.replace(DATA)


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        with LOCK:
            super().handle_one_request()

    def _send(self, code, body=None, headers=None):
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            return data if isinstance(data, dict) else None
        except ValueError:
            return None

    def do_GET(self):
        links = load()
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if self.path == "/links":
            return self._send(200, list(links.values()))
        match = re.fullmatch(r"/(links|r)/([A-Za-z0-9_-]+)", self.path)
        if not match or match.group(2) not in links:
            return self._send(404, {"error": "not found"})
        link = links[match.group(2)]
        if match.group(1) == "links":
            return self._send(200, link)
        link["visits"] += 1
        store(links)
        return self._send(302, None, {"Location": link["url"]})

    def do_POST(self):
        if self.path != "/links":
            return self._send(404, {"error": "not found"})
        body = self._body()
        url = (body or {}).get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return self._send(422, {"error": "url must start with http:// or https://"})
        links = load()
        code = body.get("code")
        if code is not None:
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code):
                return self._send(422, {"error": "invalid code"})
            if code in links:
                return self._send(409, {"error": "code taken"})
        else:
            code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            while code in links:
                code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        links[code] = {"code": code, "url": url, "visits": 0}
        store(links)
        return self._send(201, links[code])

    def do_DELETE(self):
        links = load()
        match = re.fullmatch(r"/links/([A-Za-z0-9_-]+)", self.path)
        if not match or match.group(1) not in links:
            return self._send(404, {"error": "not found"})
        del links[match.group(1)]
        store(links)
        return self._send(204)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
