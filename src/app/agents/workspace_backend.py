"""The workspace an agent sees, without the machinery that runs it.

The sandbox points HOME at `.agent-home` inside the workspace, so npm, pip and
cargo caches land per-run instead of in a directory every run shares. In
container mode that placement is not a choice: only the workspace is mounted,
so anything a command writes has to be inside it.

The cost is that it is also inside everything an agent looks at. Measured on
run-61c5a5b6: 42 tool results across ten stages carried `.agent-home`, every
`ls /` opened with it, and one `npm install` had left 26 cache blobs with
sha512 filenames. `list_repository_files` was taught to skip it; `ls`, `glob`
and `grep` come from the deep-agent filesystem backend and were not.

This wraps that backend so all three agree. It is the agent's *view* that
changes - the directory is still there, still writable, and the sandbox still
uses it - which is the distinction that matters: hiding it from a listing must
not mean a command cannot write to it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from deepagents.backends.filesystem import FilesystemBackend

#: Directory names hidden from an agent's view of the workspace. Sourced from
#: the repository tools so the two listings cannot drift apart.
from app.tools.repository import IGNORED_DIRECTORIES


def _path_of(entry: Any) -> str:
    """The path an entry names, whatever shape the backend returned it in.

    Entries arrive as dicts (`{"path": ..., "is_dir": ...}`), as objects with a
    `.path`, or as bare strings depending on the call. Matching against the
    string form of the whole entry would work by accident and break on the
    first entry whose other fields happened to contain a directory name.
    """
    if isinstance(entry, dict):
        return str(entry.get("path", ""))
    return str(getattr(entry, "path", entry) or "")


def _is_hidden(entry: Any) -> bool:
    """Whether an entry lies in a directory agents are not shown."""
    parts = [part for part in _path_of(entry).replace("\\", "/").split("/") if part]
    return any(part in IGNORED_DIRECTORIES for part in parts)


class WorkspaceBackend(FilesystemBackend):
    """A `FilesystemBackend` that omits the run's own machinery from listings.

    Only the three tools that enumerate are filtered. `read` is deliberately
    untouched: an agent that names a path inside one of these directories has a
    reason, and a read that silently failed would be a worse surprise than a
    listing that is quiet about the cache.
    """

    def ls(self, path: str) -> Any:
        result = super().ls(path)
        entries = getattr(result, "entries", None)
        if not entries:
            return result
        return replace(result, entries=[e for e in entries if not _is_hidden(e)])

    def glob(self, pattern: str, path: str | None = None) -> Any:
        result = super().glob(pattern, path)
        matches = getattr(result, "matches", None)
        if not matches:
            return result
        return replace(result, matches=[m for m in matches if not _is_hidden(m)])

    def grep(self, *args: Any, **kwargs: Any) -> Any:
        result = super().grep(*args, **kwargs)
        matches = getattr(result, "matches", None)
        if not matches:
            return result
        return replace(result, matches=[m for m in matches if not _is_hidden(m)])


__all__ = ["WorkspaceBackend"]
