#!/usr/bin/env python3
"""Dump everything about one run to a single JSON file, for offline audit.

Run this on the machine where DevFlow is up (the one serving localhost:8000):

    python scratch/export_run.py run-5696a52d-a778-4faa-8cce-d6bf056ee255

Credentials come from --user/--password or the DEVFLOW_USER / DEVFLOW_PASSWORD
environment variables, so nothing secret has to be typed into a shell history.
The output file is written next to this script and contains the run's status,
its full log stream (paged, not just the first 500), its stage list, its
artifact index and the wizard model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

try:
    import httpx
except ImportError:  # pragma: no cover - convenience for a bare interpreter
    sys.exit("pip install httpx (or run this inside the app container)")

DEFAULT_BASE = os.environ.get("DEVFLOW_BASE_URL", "http://127.0.0.1:8000")


def fetch_all_logs(client: httpx.Client, run_id: str) -> list[dict]:
    """Page through /logs until the server stops handing back new events.

    The endpoint caps `limit`, so a single request silently truncates a long
    run -- which is exactly the case worth auditing.
    """
    out: list[dict] = []
    offset = 0
    while True:
        resp = client.get(
            f"/api/runs/{quote(run_id)}/logs",
            params={"limit": 500, "offset": offset},
        )
        resp.raise_for_status()
        body = resp.json()
        page = body.get("logs") or []
        out.extend(page)
        total = body.get("total")
        offset += len(page)
        if not page or (isinstance(total, int) and offset >= total):
            break
    return out


def get(client: httpx.Client, path: str) -> object:
    """GET one endpoint, recording the failure rather than aborting the dump."""
    try:
        resp = client.get(path)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - a partial dump beats none
        return {"_error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--user", default=os.environ.get("DEVFLOW_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("DEVFLOW_PASSWORD"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if not args.password:
        return int(bool(sys.stderr.write(
            "No password. Pass --password or set DEVFLOW_PASSWORD.\n"
        ))) or 2

    run_id = args.run_id
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        token = client.post(
            "/api/auth/token",
            data={"username": args.user, "password": args.password},
        )
        token.raise_for_status()
        client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

        bundle = {
            "run_id": run_id,
            "status": get(client, f"/api/runs/{quote(run_id)}"),
            "stages": get(client, f"/api/runs/{quote(run_id)}/stages"),
            "artifacts": get(client, f"/api/runs/{quote(run_id)}/artifacts"),
            "wizard": get(client, f"/api/runs/{quote(run_id)}/wizard"),
            "approval": get(client, f"/api/runs/{quote(run_id)}/approval"),
            "logs": fetch_all_logs(client, run_id),
        }

    out = Path(args.out or Path(__file__).with_name(f"{run_id}.json"))
    out.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, "
          f"{len(bundle['logs'])} log events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
