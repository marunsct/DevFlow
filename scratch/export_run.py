#!/usr/bin/env python3
"""Dump everything about one run to a single JSON file, for offline audit.

Run it on the machine serving the app, from the repository root:

    python3 scratch/export_run.py run-5696a52d-a778-4faa-8cce-d6bf056ee255

The standard library only, so there is nothing to install, and the admin
password and port are read from the `.env` beside this repository unless
given - so nothing secret has to be typed into a shell history. Override
with --password / --base-url, or DEVFLOW_PASSWORD / DEVFLOW_BASE_URL.

The output holds the run's status, its full log stream (paged, because the
endpoint caps a single request at 500 and a run worth auditing is longer
than that), its stage list, its artifact index, the wizard model and the
approval state.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def from_dotenv(name: str) -> str | None:
    """One value out of the repository's .env, or None.

    Deliberately not a parser: `KEY=value`, optional `export`, optional
    quotes, `#` comments. That is the whole of what this file holds.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return None
    try:
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"") or None
    except OSError:
        return None
    return None


class Client:
    """The few requests this needs, over urllib, carrying a bearer token."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def _open(self, request: urllib.request.Request) -> object:
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    def login(self, username: str, password: str) -> None:
        body = urllib.parse.urlencode(
            {"username": username, "password": password}
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/auth/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.token = self._open(request)["access_token"]

    def get(self, path: str, **params: object) -> object:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._open(urllib.request.Request(url))

    def get_or_record(self, path: str) -> object:
        """GET, keeping a failure in the bundle rather than aborting the dump."""
        try:
            return self.get(path)
        except Exception as exc:  # noqa: BLE001 - a partial dump beats none
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                detail = f" {exc.read()[:400].decode('utf-8', 'replace')}"
            return {"_error": f"{type(exc).__name__}: {exc}{detail}"}


def fetch_all_logs(client: Client, run_id: str) -> list[dict]:
    """Every event, not the first page.

    `limit` is capped at 500 server-side, so one request silently truncates
    the long run - which is the one worth auditing.
    """
    out: list[dict] = []
    offset = 0
    while True:
        body = client.get(f"/api/runs/{run_id}/logs", limit=500, offset=offset)
        page = body.get("logs") or []
        out.extend(page)
        total = body.get("total")
        offset += len(page)
        if not page or (isinstance(total, int) and offset >= total):
            return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_id")
    parser.add_argument("--base-url")
    parser.add_argument("--user", default=os.environ.get("DEVFLOW_USER", "admin"))
    parser.add_argument("--password")
    parser.add_argument("--out")
    args = parser.parse_args()

    port = os.environ.get("APP_PORT") or from_dotenv("APP_PORT") or "8000"
    base_url = (
        args.base_url
        or os.environ.get("DEVFLOW_BASE_URL")
        or f"http://127.0.0.1:{port}"
    )
    password = (
        args.password
        or os.environ.get("DEVFLOW_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD")
        or from_dotenv("ADMIN_PASSWORD")
    )
    if not password:
        print(
            "No admin password found. Set ADMIN_PASSWORD in .env, or pass "
            "--password.",
            file=sys.stderr,
        )
        return 2

    run_id = urllib.parse.quote(args.run_id, safe="")
    client = Client(base_url)
    try:
        client.login(args.user, password)
    except urllib.error.HTTPError as exc:
        print(f"Login failed ({exc.code}) at {base_url}.", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Cannot reach {base_url}: {exc}", file=sys.stderr)
        return 2

    bundle = {
        "run_id": args.run_id,
        "base_url": base_url,
        "status": client.get_or_record(f"/api/runs/{run_id}"),
        "stages": client.get_or_record(f"/api/runs/{run_id}/stages"),
        "artifacts": client.get_or_record(f"/api/runs/{run_id}/artifacts"),
        "wizard": client.get_or_record(f"/api/runs/{run_id}/wizard"),
        "approval": client.get_or_record(f"/api/runs/{run_id}/approval"),
    }
    try:
        bundle["logs"] = fetch_all_logs(client, run_id)
    except Exception as exc:  # noqa: BLE001
        bundle["logs"] = []
        bundle["_logs_error"] = f"{type(exc).__name__}: {exc}"

    out = Path(args.out or REPO_ROOT / "scratch" / f"{args.run_id}.json")
    out.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    print(
        f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, "
        f"{len(bundle['logs'])} log events)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
