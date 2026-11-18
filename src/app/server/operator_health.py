"""`GET /api/health/operator`: what an operator of one compose host needs to see at a glance (deep review 2026-11-18, F5).

Measured on the host the harness runs on: the disk filled and crashed the database, deploys paused runs, and only an
operator reading `loop.sh` output knew the state of the machine. One read-only page now says: free space on the data
volume, whether the database answers, the runs running and the runs waiting for a worker (with their place), whether
the build model's server is reachable (its status endpoint, never a model call), how old the newest backup is, and the
harness's version. Every part is read separately and a part that cannot be read says so; nothing here changes
anything.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

#: Free space under which the data volume is low: whichever of the two is larger.
LOW_FREE_SHARE = 0.10
LOW_FREE_BYTES = 5 * 1024**3
#: A newest backup older than this is stale: backups run nightly.
STALE_BACKUP_HOURS = 36
OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"


def data_directory() -> Path:
    """Where runs keep their workspaces, uploads and transcripts: the volume a full disk stops."""
    for name in ("DATA_DIR", "WORKFLOW_WORKSPACE_ROOT"):
        value = os.environ.get(name, "").strip()
        if value:
            path = Path(value)
            while not path.exists() and path != path.parent:
                path = path.parent
            return path
    return Path("data") if Path("data").exists() else Path(".")


def disk(path: Path, usage: Callable[[Path], Any] = shutil.disk_usage) -> dict[str, Any]:
    """Free space on the volume holding `path`; low under 10% or 5 GiB."""
    try:
        found = usage(path)
    except OSError as error:
        return {"status": UNKNOWN, "path": str(path), "said": f"Could not read the volume: {error.strerror or error}."}
    share = found.free / found.total if found.total else 0.0
    low = share < LOW_FREE_SHARE or found.free < LOW_FREE_BYTES
    gib = found.free / 1024**3
    return {"status": WARN if low else OK, "path": str(path), "free_bytes": found.free, "total_bytes": found.total,
            "free_share": round(share, 3),
            "said": (f"{gib:.1f} GiB free ({share:.0%})." + (" Low: a full disk stops the database and every run; "
                     "clear old workspaces, logs or images." if low else ""))}


def newest_backup(directory: str, now: datetime) -> dict[str, Any]:
    """The newest backup under `directory` (one folder or file per backup, or under `daily/`) and its age."""
    if not directory:
        return {"status": UNKNOWN, "said": "No backup folder is visible to the server: set BACKUP_DIR to the folder "
                                           "the backups are written to, mounted read-only, to see their age here."}
    root = Path(directory)
    try:
        places = [p for base in (root, root / "daily") if base.is_dir() for p in base.iterdir() if p.name != "daily"]
    except OSError as error:
        return {"status": UNKNOWN, "said": f"The backup folder could not be read: {error.strerror or error}."}
    if not places:
        return {"status": FAIL, "said": f"No backup in {directory}."}
    newest = max(places, key=lambda p: p.stat().st_mtime)
    at = datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)
    hours = round((now - at).total_seconds() / 3600, 1)
    stale = hours > STALE_BACKUP_HOURS
    return {"status": WARN if stale else OK, "newest": newest.name, "at": at.isoformat(), "age_hours": hours,
            "said": f"The newest backup, {newest.name}, is {hours:g} hours old." + (
                " Stale: backups should run nightly." if stale else "")}


def waiting_runs(records: Iterable[Any], activity: Callable[[str], datetime | None],
                 now: datetime) -> list[dict[str, Any]]:
    """Runs marked running that have not begun: no record yet, so waiting for a worker; oldest first, with a place."""
    def when(value: Any) -> datetime | None:
        try:
            found = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        return found if found.tzinfo else found.replace(tzinfo=timezone.utc)

    waiting = []
    for record in records:
        if str(getattr(record, "status", "")) != "running" or activity(record.run_id) is not None:
            continue
        since = when(getattr(record, "updated_at", None)) or now
        waiting.append({"run_id": record.run_id, "name": getattr(record, "run_name", None) or "",
                        "since": since.isoformat(), "minutes": int((now - since).total_seconds() // 60)})
    waiting.sort(key=lambda w: w["since"])
    for place, run in enumerate(waiting, 1):
        run["position"] = place
    return waiting


def overall(parts: dict[str, dict[str, Any]]) -> str:
    statuses = {part.get("status") for part in parts.values()}
    return FAIL if FAIL in statuses else WARN if WARN in statuses or UNKNOWN in statuses else OK


__all__ = ["FAIL", "OK", "UNKNOWN", "WARN", "data_directory", "disk", "newest_backup", "overall", "waiting_runs"]
