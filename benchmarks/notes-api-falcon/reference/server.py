"""Reference implementation of the notes-api benchmark (standard library only)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "data")) / "notes.json"


def load():
    return json.loads(DATA.read_text()) if DATA.exists() else {"next": 1, "notes": []}


def store(db):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(db))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=None):
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self):
        try:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return {}

    def _note_id(self):
        parts = self.path.strip("/").split("/")
        return int(parts[1]) if len(parts) == 2 and parts[0] == "notes" and parts[1].isdigit() else None

    def do_GET(self):
        db = load()
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if self.path == "/notes":
            return self._send(200, db["notes"])
        note_id = self._note_id()
        found = [n for n in db["notes"] if n["id"] == note_id]
        return self._send(200, found[0]) if found else self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/notes":
            return self._send(404, {"error": "not found"})
        body = self._body()
        if not str(body.get("title") or "").strip():
            return self._send(422, {"error": "title required"})
        db = load()
        note = {"id": db["next"], "title": body["title"], "body": str(body.get("body") or "")}
        db["next"] += 1
        db["notes"].append(note)
        store(db)
        return self._send(201, note)

    def do_PUT(self):
        db, note_id, body = load(), self._note_id(), self._body()
        found = [n for n in db["notes"] if n["id"] == note_id]
        if not found:
            return self._send(404, {"error": "not found"})
        if not str(body.get("title") or "").strip():
            return self._send(422, {"error": "title required"})
        found[0].update(title=body["title"], body=str(body.get("body") or ""))
        store(db)
        return self._send(200, found[0])

    def do_DELETE(self):
        db, note_id = load(), self._note_id()
        remaining = [n for n in db["notes"] if n["id"] != note_id]
        if len(remaining) == len(db["notes"]):
            return self._send(404, {"error": "not found"})
        db["notes"] = remaining
        store(db)
        return self._send(204)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
