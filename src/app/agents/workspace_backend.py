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

import hashlib
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


#: After this many identical reads of unchanged bytes, say so. The second read
#: of a file is ordinary - a model checks its work. The sixth is a loop.
REPEATS_BEFORE_SAYING_SO = 2


class _NoticingRepeats:
    """Say when a file comes back byte-identical to the last time it was read.

    Measured on run-44e9fc83's `specialist_backend_1`: 39 tool calls, 17 of
    them the same `read_file` of `app.js` at the same range, in runs of six,
    five and four, two to three seconds apart, with no write between them.
    That is 16 model turns spent re-reading 400 lines the model already had.

    Keyed on the CONTENT, not on whether a write happened. A specialist that
    edits a file and reads it back gets different bytes and no note, which is
    the case that makes write-tracking necessary everywhere else; here the
    bytes answer the question directly.

    The content is always returned. A note that withheld it would strand a
    model that had genuinely lost the text - and while compaction is not
    firing on these stages today (it triggers at 70,200 tokens and the largest
    stage of run-1d1b6c9c carried about 22,600), a fix whose failure mode is
    "the agent cannot get its file back" is not worth the tokens it saves.

    The note is delivered in the result the model just asked for, which is
    where correction has been shown to work on this pipeline: the "there is a
    file of that name at ..." hint changed behaviour on the very next call,
    while the same guidance in a brief changed nothing.
    """

    def _note_if_repeated(self, key: str, text: str) -> str:
        seen = getattr(self, "_read_digests", None)
        if seen is None:
            seen = {}
            self._read_digests = seen  # noqa: SLF001 - own attribute
        digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        previous, count = seen.get(key, (None, 0))
        if previous == digest:
            count += 1
            seen[key] = (digest, count)
            if count >= REPEATS_BEFORE_SAYING_SO:
                return (
                    f"\n\n[This file is byte-identical to the {count} previous "
                    "times you read it in this stage. Nothing has changed it. "
                    "Reading it again will return exactly this. Use what you "
                    "have and move on.]"
                )
            return ""
        seen[key] = (digest, 0)
        return ""


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


class WorkspaceBackend(_Suggesting, _NoticingRepeats, FilesystemBackend):
    """A `FilesystemBackend` that omits the run's own machinery from listings.

    Only the three tools that enumerate are filtered. `read` is deliberately
    untouched: an agent that names a path inside one of these directories has a
    reason, and a read that silently failed would be a worse surprise than a
    listing that is quiet about the cache.
    """

    def read(self, file_path: str, *args: Any, **kwargs: Any) -> Any:
        result = super().read(file_path, *args, **kwargs)
        error = getattr(result, "error", None)
        if error:
            if "not found" not in error:
                return result
            hint = self._where_it_actually_is(file_path)
            return replace(result, error=error + hint) if hint else result

        # The text lives in `file_data["content"]`, not on the result itself.
        # Reading the wrong attribute made this a silent no-op, which is the
        # quietest kind of broken: every test that asked "did it fail?" passed.
        data = getattr(result, "file_data", None)
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, str):
            return result
        note = self._note_if_repeated(f"{file_path}|{args}|{sorted(kwargs.items())}", content)
        if not note:
            return result
        return replace(result, file_data={**data, "content": content + note})

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
