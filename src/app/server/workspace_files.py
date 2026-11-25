"""The run page's workspace view: the product's files as they are written, read-only (plan WS.1).

The tree is the listing every stage sees (`list_repository_files`), so `.git`, the harness's own records, installed
and build folders and credential files are left out by the one set of rules; a file is shown only when that listing
would name it, and searched (plan UX.7) only then too. Nothing here writes.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

#: Files listed at most; a larger workspace says the tree is cut short.
MOST_FILES = 5_000
#: Bytes of one file shown at most: a code view, not a download.
MOST_FILE_BYTES = 512 * 1024
#: Search hits returned at most, in all and from one file; characters of a hit's line; seconds one search may take.
MOST_HITS = 500
MOST_HITS_PER_FILE = 50
MOST_LINE_CHARS = 240
SEARCH_SECONDS = 3.0


class NotShown(ValueError):
    """The path is not one of the workspace's listed files."""


class NotReadable(ValueError):
    """A listed file the view does not show: too large, or not text."""


def tree(root: str | Path) -> dict[str, Any]:
    """The listed files with their sizes, and which changed since the last accepted sprint."""
    from app.server.changes import ChangesUnavailable, accepted_base
    from app.tools.repository import list_repository_files
    from app.tools.version_control import changed_since

    root = Path(root)
    listed = list_repository_files(root)
    files = []
    for relative in listed[:MOST_FILES]:
        try:
            files.append({"path": relative, "size": (root / relative).stat().st_size})
        except OSError:
            continue  # removed between the listing and now
    shown = {entry["path"] for entry in files}
    since, changed = None, []
    if (root / ".git").exists():
        try:
            base, since = accepted_base(root)
            changed = [path for path in changed_since(root, base) if path in shown] if base else []
        except ChangesUnavailable:
            since, changed = None, []
    return {"files": files, "truncated": len(listed) > MOST_FILES, "since": since, "changed": changed}


def read(root: str | Path, relative: str) -> str:
    """One listed file's text; `NotShown` for a path the tree hides, `NotReadable` for one too large or binary."""
    from app.tools.repository import is_listed

    if not is_listed(root, relative):
        raise NotShown(f"Not a file of this workspace: {relative}")
    path = Path(root) / relative
    if path.stat().st_size > MOST_FILE_BYTES:
        raise NotReadable(f"{relative} is larger than {MOST_FILE_BYTES // 1024} KB; download it instead.")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise NotReadable(f"{relative} is not text; download it instead.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NotReadable(f"{relative} is not UTF-8 text; download it instead.") from error


def digest(text: str) -> str:
    """The hash of a file's text as it is shown: what an editor names when it asks whether the file has moved on."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def search(
    root: str | Path,
    query: str,
    *,
    case_sensitive: bool = False,
    most_hits: int = MOST_HITS,
    seconds: float = SEARCH_SECONDS,
) -> dict[str, Any]:
    """The lines of the listed files that hold `query`, as plain text (never a pattern), capped in hits and in time.

    Only what the tree lists is searched, each path judged where it leads: a link to a hidden or outside file is
    skipped, as are files too large or not text for `read`. `truncated` says hits were left out; `timed_out` that
    files were left unsearched.
    """
    from app.tools.repository import list_repository_files

    root = Path(root).expanduser().resolve()
    deadline = time.monotonic() + seconds
    needle = query if case_sensitive else query.lower()
    listed = list_repository_files(root)[:MOST_FILES]
    shown = set(listed)
    hits: list[dict[str, Any]] = []
    truncated = timed_out = False
    searched = 0
    for relative in listed:
        if len(hits) >= most_hits and truncated:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        try:
            target = (root / relative).resolve()
            if target.relative_to(root).as_posix() not in shown or target.stat().st_size > MOST_FILE_BYTES:
                continue
            data = target.read_bytes()
        except (OSError, ValueError):
            continue  # removed since the listing, or leading out of the workspace
        if b"\x00" in data[:8192]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        searched += 1
        in_file = 0
        for number, line in enumerate(text.splitlines(), start=1):
            column = (line if case_sensitive else line.lower()).find(needle)
            if column < 0:
                continue
            if len(hits) >= most_hits or in_file >= MOST_HITS_PER_FILE:
                truncated = True
                break
            hits.append({"path": relative, "line": number, "column": column + 1, "text": line[:MOST_LINE_CHARS]})
            in_file += 1
    return {"query": query, "hits": hits, "truncated": truncated, "timed_out": timed_out, "files_searched": searched}
