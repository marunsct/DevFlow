"""Keeps the part of a tool's output that did not fit in the context.

`SandboxExecutor` truncates output at `MAX_OUTPUT_SIZE`; without this the
discarded remainder is gone, which matters most exactly when it matters at all -
a failing build whose real error was past the cap.

Written under DATA_DIR, not the workspace, for the same reason as the context
store: the workspace is product output and is archived and shown as such.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path

DEFAULT_RETENTION_HOURS = 72
"""How long a journalled output stays readable, unless configured otherwise.

Long enough to investigate a failure from a few days ago, short enough that a
worker producing large build logs does not fill the shared `appdata` volume.
Set `CTX_JOURNAL_RETENTION_HOURS=0` to keep entries forever.
"""

_PRUNE_INTERVAL_SECONDS = 3600.0
"""How often one process may prune, at most.

Pruning walks the directory, so doing it on every write would put a directory
scan in front of every truncated command. Once an hour per process is enough:
the bound this enforces is an age, not a size.
"""

_last_prune_at = 0.0

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def journal_root() -> Path:
    configured = os.environ.get("CTX_JOURNAL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "journal").expanduser().resolve()


def retention_seconds() -> float:
    """Age at which a journal entry may be deleted; 0 disables pruning.

    Never raises: a malformed value logs and falls back to the default, the
    same convention as `ContextPolicy.from_environment`.
    """
    raw = os.environ.get("CTX_JOURNAL_RETENTION_HOURS", "").strip()
    if not raw:
        return DEFAULT_RETENTION_HOURS * 3600.0
    try:
        hours = float(raw)
    except ValueError:
        logger.warning(
            "Malformed CTX_JOURNAL_RETENTION_HOURS=%r; using %d hours",
            raw, DEFAULT_RETENTION_HOURS,
        )
        return DEFAULT_RETENTION_HOURS * 3600.0
    return max(hours, 0.0) * 3600.0


def prune(now: float | None = None) -> int:
    """Delete journal entries older than the retention window.

    Returns how many were removed. Never raises: this runs on the path of a
    command that already succeeded, and losing a cleanup must not fail it.

    Age is taken from mtime, so an entry still being written is never old.
    """
    window = retention_seconds()
    if window <= 0:
        return 0
    reference = time.time() if now is None else now
    removed = 0
    try:
        directory = journal_root()
        if not directory.is_dir():
            return 0
        for path in directory.iterdir():
            try:
                if not path.is_file() or path.suffix != ".log":
                    continue
                if reference - path.stat().st_mtime <= window:
                    continue
                path.unlink()
                removed += 1
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - cleanup is never load-bearing
        logger.warning("Could not prune the journal", exc_info=True)
    return removed


def _prune_if_due() -> None:
    """Prune at most once per `_PRUNE_INTERVAL_SECONDS` in this process."""
    global _last_prune_at
    now = time.time()
    if now - _last_prune_at < _PRUNE_INTERVAL_SECONDS:
        return
    _last_prune_at = now
    prune(now)


def write_entry(label: str, content: str) -> str | None:
    """Store `content` and return a short reference, or None if it could not be.

    Never raises. Losing a log copy must not fail the command that produced it.
    """
    if not content:
        return None
    _prune_if_due()
    try:
        safe = _UNSAFE.sub("-", label).strip("-")[:60] or "output"
        directory = journal_root()
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time())}-{safe}-{uuid.uuid4().hex[:8]}.log"
        (directory / name).write_text(content, encoding="utf-8")
        return name
    except OSError:
        logger.warning("Could not write journal entry for %s", label, exc_info=True)
        return None


def read_entry(name: str) -> str | None:
    """Read one entry back by the name `write_entry` returned."""
    safe = _UNSAFE.sub("-", name).strip("-")
    path = journal_root() / safe
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


__all__ = [
    "DEFAULT_RETENTION_HOURS",
    "journal_root",
    "prune",
    "read_entry",
    "retention_seconds",
    "write_entry",
]
