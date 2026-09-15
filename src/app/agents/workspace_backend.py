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

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from deepagents.backends.filesystem import FilesystemBackend

#: Directory names hidden from an agent's view of the workspace. Sourced from
#: the repository tools so the two listings cannot drift apart.
from app.tools.repository import IGNORED_DIRECTORIES



#: Beyond this, a suggestion is a list rather than an answer.
MAX_SUGGESTIONS = 3


def _basename(path: str) -> str:
    return os.path.basename(str(path).rstrip("/")) or str(path)


class _Suggesting:
    """Turn "not found" into "not found, and here is where it is".

    An agent that guesses a path prefix gets an error naming the path it
    invented and nothing else, so it guesses again. Measured across the stored
    runs, the guesses are `/home/user/...`, `/workspace/...`, the project
    directory at the root, and the host path; and the file it wants almost
    always exists. On run-3f8e387d - the run that died of gate exhaustion -
    72 reads failed and 56 of them (77%) named a file that was in the
    workspace under a different path.

    The lookup is by basename, which is the part an agent gets right. It costs
    one directory walk on a path that has already failed, and nothing at all
    on the normal path.
    """

    def _where_it_actually_is(self, wanted: str) -> str:
        root = getattr(self, "cwd", None)
        name = _basename(wanted)
        if not root or not name:
            return ""
        # A name with no extension is a directory name, which is what `ls`
        # misses: run-2eb3aa24 asked for `/simple-to-do-list-app` four times.
        want_file = "." in name
        try:
            found = [
                str(candidate.relative_to(root))
                for candidate in Path(root).rglob(name)
                if (candidate.is_file() if want_file else candidate.is_dir())
                and not any(part in IGNORED_DIRECTORIES for part in candidate.parts)
            ]
        except Exception:  # noqa: BLE001 - a hint must never fail the call
            return ""
        if not found:
            return ""
        kind = "a file" if want_file else "a directory"
        shown = ", ".join(f"/{path}" for path in sorted(found)[:MAX_SUGGESTIONS])
        more = "" if len(found) <= MAX_SUGGESTIONS else f" and {len(found) - MAX_SUGGESTIONS} more"
        return (
            f" There is {kind} of that name at {shown}{more}. "
            "Every path is relative to the workspace root, which is '/'."
        )


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


class WorkspaceBackend(_Suggesting, FilesystemBackend):
    """A `FilesystemBackend` that omits the run's own machinery from listings.

    Only the three tools that enumerate are filtered. `read` is deliberately
    untouched: an agent that names a path inside one of these directories has a
    reason, and a read that silently failed would be a worse surprise than a
    listing that is quiet about the cache.
    """

    def read(self, file_path: str, *args: Any, **kwargs: Any) -> Any:
        result = super().read(file_path, *args, **kwargs)
        error = getattr(result, "error", None)
        if not error or "not found" not in error:
            return result
        hint = self._where_it_actually_is(file_path)
        return replace(result, error=error + hint) if hint else result

    def ls(self, path: str) -> Any:
        result = super().ls(path)
        error = getattr(result, "error", None)
        if error and "path_not_found" in error:
            hint = self._where_it_actually_is(path)
            return replace(result, error=error + hint) if hint else result
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
