"""Reference for the tasks-api-change benchmark: the tasks-api service with due dates, a done filter and a summary."""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

DATA = Path(os.environ.get("DATA_DIR", "data"))
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()
DB = sqlite3.connect(DATA / "tasks.db", check_same_thread=False)
DB.executescript(
    "CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt TEXT, hash TEXT);"
    "CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY, name TEXT);"
    "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT, title TEXT, done INTEGER);"
)
if "due" not in [column[1] for column in DB.execute("PRAGMA table_info(items)")]:
    DB.execute("ALTER TABLE items ADD COLUMN due TEXT")
    DB.commit()


def _due(value):
    """The date string when `value` is a real YYYY-MM-DD date or None; raises ValueError otherwise."""
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(value)
    return date.fromisoformat(value).isoformat()


def _item(row):
    return {"id": row[0], "title": row[1], "done": bool(row[2]), "due": row[3]}


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=None):
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _who(self):
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        with LOCK:
            row = DB.execute("SELECT name FROM tokens WHERE token = ?", (auth[7:],)).fetchone()
        return row[0] if row else None

    def _item_id(self):
        parts = self.path.strip("/").split("/")
        return int(parts[1]) if len(parts) == 2 and parts[0] == "items" and parts[1].isdigit() else None

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/health":
            return self._send(200, {"status": "ok"})
        if url.path not in ("/items", "/items/stats"):
            return self._send(404, {"error": "not found"})
        who = self._who()
        if who is None:
            return self._send(401, {"error": "sign in first"})
        with LOCK:
            rows = DB.execute("SELECT id, title, done, due FROM items WHERE owner = ? ORDER BY id", (who,)).fetchall()
        if url.path == "/items/stats":
            today = datetime.now(timezone.utc).date().isoformat()
            return self._send(200, {"total": len(rows), "done": sum(1 for r in rows if r[2]),
                                    "overdue": sum(1 for r in rows if not r[2] and r[3] and r[3] < today)})
        wanted = (parse_qs(url.query).get("done") or [None])[0]
        if wanted in ("true", "false"):
            rows = [r for r in rows if bool(r[2]) == (wanted == "true")]
        self._send(200, [_item(r) for r in rows])

    def do_POST(self):
        body = self._body()
        if self.path in ("/signup", "/signin"):
            name, password = str(body.get("username") or ""), str(body.get("password") or "")
            if not name or not password:
                return self._send(422, {"error": "username and password are required"})
            with LOCK:
                row = DB.execute("SELECT salt, hash FROM users WHERE name = ?", (name,)).fetchone()
                if self.path == "/signup":
                    if row:
                        return self._send(409, {"error": "that username is taken"})
                    salt = secrets.token_hex(8)
                    DB.execute("INSERT INTO users VALUES (?, ?, ?)", (name, salt, _hash(password, salt)))
                    DB.commit()
                    return self._send(201, {"username": name})
                if not row or _hash(password, row[0]) != row[1]:
                    return self._send(401, {"error": "wrong username or password"})
                token = secrets.token_urlsafe(24)
                DB.execute("INSERT INTO tokens VALUES (?, ?)", (token, name))
                DB.commit()
            return self._send(200, {"token": token})
        if self.path != "/items":
            return self._send(404, {"error": "not found"})
        who = self._who()
        if who is None:
            return self._send(401, {"error": "sign in first"})
        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            return self._send(422, {"error": "a title is required"})
        try:
            due = _due(body.get("due"))
        except ValueError:
            return self._send(422, {"error": "due must be a YYYY-MM-DD date"})
        with LOCK:
            cursor = DB.execute("INSERT INTO items (owner, title, done, due) VALUES (?, ?, 0, ?)", (who, title, due))
            DB.commit()
        self._send(201, {"id": cursor.lastrowid, "title": title, "done": False, "due": due})

    def _own(self, who, item_id):
        with LOCK:
            return DB.execute("SELECT id, title, done, due FROM items WHERE id = ? AND owner = ?", (item_id, who)).fetchone()

    def do_PATCH(self):
        who, item_id = self._who(), self._item_id()
        if who is None:
            return self._send(401, {"error": "sign in first"})
        row = self._own(who, item_id) if item_id is not None else None
        if not row:
            return self._send(404, {"error": "no such item"})
        body = self._body()
        done, due = bool(row[2]), row[3]
        if "done" in body:
            if not isinstance(body["done"], bool):
                return self._send(422, {"error": "done must be true or false"})
            done = body["done"]
        if "due" in body:
            try:
                due = _due(body["due"])
            except ValueError:
                return self._send(422, {"error": "due must be a YYYY-MM-DD date"})
        if "done" not in body and "due" not in body:
            return self._send(422, {"error": "done must be true or false"})
        with LOCK:
            DB.execute("UPDATE items SET done = ?, due = ? WHERE id = ?", (int(done), due, item_id))
            DB.commit()
        self._send(200, {"id": row[0], "title": row[1], "done": done, "due": due})

    def do_DELETE(self):
        who, item_id = self._who(), self._item_id()
        if who is None:
            return self._send(401, {"error": "sign in first"})
        if item_id is None or not self._own(who, item_id):
            return self._send(404, {"error": "no such item"})
        with LOCK:
            DB.execute("DELETE FROM items WHERE id = ?", (item_id,))
            DB.commit()
        self._send(204)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
