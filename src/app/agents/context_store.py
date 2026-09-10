"""Where compaction keeps what it takes out of the conversation.

`SummarizationMiddleware` requires a backend of its own, separate from the
agent's. It is used to hold content lifted out of the message history.

This is deliberately **not** the run workspace. The workspace is product
output: it is listed as run artifacts, archived to object storage when a run
finishes, and shown in the artifact viewer. Context bookkeeping in there would
appear to the user as something the product produced.

`DATA_DIR/context/<thread id>/` is per-run, survives a restart, is inspectable
when a run misbehaves, and is invisible to everything that treats the workspace
as deliverable.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def context_root() -> Path:
    """The directory under which every run's context data lives."""
    configured = os.environ.get("CTX_STORE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "context").expanduser().resolve()


def _safe_segment(value: str) -> str:
    """Reduce an identifier to one safe path segment."""
    cleaned = _UNSAFE.sub("-", Path(str(value)).name).strip("-")
    return cleaned[:120] or "thread"


def context_directory(thread_id: str) -> Path:
    """Create and return the context directory for one agent thread."""
    root = context_root()
    directory = (root / _safe_segment(thread_id)).resolve()
    if directory != root and root not in directory.parents:
        raise ValueError(f"Refusing to use a context directory outside {root}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_context_backend(thread_id: str):
    """A filesystem backend scoped to one agent thread.

    `FilesystemBackend` ships with deepagents; a hand-written backend would have
    to implement read/write/edit/ls/glob/grep/delete/upload_files/download_files
    plus their async twins, and getting any of them wrong fails at compaction
    time rather than at construction time.
    """
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(context_directory(thread_id)))


def discard_context(thread_id: str) -> None:
    """Remove one thread's context data. Never raises."""
    try:
        directory = context_directory(thread_id)
    except ValueError:
        return
    shutil.rmtree(directory, ignore_errors=True)


__all__ = [
    "build_context_backend",
    "context_directory",
    "context_root",
    "discard_context",
]
