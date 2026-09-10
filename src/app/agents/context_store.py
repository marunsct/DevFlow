"""Where compaction keeps what it takes out of the conversation.

`SummarizationMiddleware` requires a backend of its own, separate from the
agent's. It is used to hold content lifted out of the message history.

This is deliberately **not** the run workspace. The workspace is product output:
it is listed as run artifacts, archived to object storage when a run finishes,
and shown in the artifact viewer. Context bookkeeping in there would appear to
the user as something the product produced.

Keyed by **agent name**, not by run or thread. The thread id is not known when
the middleware is constructed - `_run_gated_agent` mints a fresh one per attempt
- so an agent name is the only stable key available, and it is adequate because
the content is scratch space for the summariser rather than run state. Two runs
executing at once therefore share a directory, which is safe: deepagents names
each offloaded history `conversation_history/session_<uuid4>.md` from a
per-invocation session id, and its own source notes that these "must not collide
across independent sessions sharing a backend".

That sharing is why nothing here is deleted when a run ends - it would clobber a
concurrent run's in-flight scratch data. `prune()` bounds the tree by age
instead, which a file being written now can never trip.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")

DEFAULT_RETENTION_HOURS = 72
"""How long an evicted-history file stays on disk, unless configured otherwise.

Set `CTX_CONTEXT_RETENTION_HOURS=0` to keep them forever.

Pruning is by age rather than by run, and that is deliberate. The worker runs
`--concurrency=${CELERY_CONCURRENCY:-2}`, so two runs share these per-agent
directories; deleting a directory when one run ends would clobber the other
run's in-flight scratch data. An age bound cannot: a file being written now has
a current mtime.
"""


def context_root() -> Path:
    """The directory under which every run's context data lives."""
    configured = os.environ.get("CTX_STORE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "context").expanduser().resolve()


def _safe_segment(value: str) -> str:
    """Reduce an identifier to one safe path segment."""
    cleaned = _UNSAFE.sub("-", Path(str(value)).name).strip("-")
    return cleaned[:120] or "unnamed"


def context_directory(key: str) -> Path:
    """Create and return the context directory for one key (an agent name)."""
    root = context_root()
    directory = (root / _safe_segment(key)).resolve()
    if directory != root and root not in directory.parents:
        raise ValueError(f"Refusing to use a context directory outside {root}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_context_backend(key: str):
    """A filesystem backend scoped to one key - in practice, one agent name.

    `FilesystemBackend` ships with deepagents; a hand-written backend would have
    to implement read/write/edit/ls/glob/grep/delete/upload_files/download_files
    plus their async twins, and getting any of them wrong fails at compaction
    time rather than at construction time.
    """
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(context_directory(key)))


def discard_context(key: str) -> None:
    """Remove one key's context data. Never raises.

    Not called at run end - see the module docstring for why that would be
    unsafe. Kept because it is the right tool for clearing one misbehaving
    agent's scratch space by hand.
    """
    try:
        directory = context_directory(key)
    except ValueError:
        return
    shutil.rmtree(directory, ignore_errors=True)


def retention_seconds() -> float:
    """Age at which an evicted-history file may be deleted; 0 disables pruning."""
    raw = os.environ.get("CTX_CONTEXT_RETENTION_HOURS", "").strip()
    if not raw:
        return DEFAULT_RETENTION_HOURS * 3600.0
    try:
        hours = float(raw)
    except ValueError:
        logger.warning(
            "Malformed CTX_CONTEXT_RETENTION_HOURS=%r; using %d hours",
            raw, DEFAULT_RETENTION_HOURS,
        )
        return DEFAULT_RETENTION_HOURS * 3600.0
    return max(hours, 0.0) * 3600.0


def prune(now: float | None = None) -> int:
    """Delete context files older than the retention window. Never raises.

    Files only; empty directories are left alone. A per-agent directory is
    recreated on the agent's next run anyway, and removing one that a concurrent
    run is about to write into buys nothing.
    """
    window = retention_seconds()
    if window <= 0:
        return 0
    reference = time.time() if now is None else now
    removed = 0
    try:
        root = context_root()
        if not root.is_dir():
            return 0
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                if reference - path.stat().st_mtime <= window:
                    continue
                path.unlink()
                removed += 1
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - cleanup is never load-bearing
        logger.warning("Could not prune the context store", exc_info=True)
    return removed


__all__ = [
    "DEFAULT_RETENTION_HOURS",
    "build_context_backend",
    "context_directory",
    "context_root",
    "discard_context",
    "prune",
    "retention_seconds",
]
