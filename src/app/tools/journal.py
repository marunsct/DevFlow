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

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def journal_root() -> Path:
    configured = os.environ.get("CTX_JOURNAL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "journal").expanduser().resolve()


def write_entry(label: str, content: str) -> str | None:
    """Store `content` and return a short reference, or None if it could not be.

    Never raises. Losing a log copy must not fail the command that produced it.
    """
    if not content:
        return None
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


__all__ = ["journal_root", "read_entry", "write_entry"]
