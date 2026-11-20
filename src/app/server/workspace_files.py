"""The run page's workspace view: the product's files as they are written, read-only (plan WS.1).

The tree is the listing every stage sees (`list_repository_files`), so `.git`, the harness's own records, installed
and build folders and credential files are left out by the one set of rules; a file is shown only when that listing
would name it. Nothing here writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Files listed at most; a larger workspace says the tree is cut short.
MOST_FILES = 5_000
#: Bytes of one file shown at most: a code view, not a download.
MOST_FILE_BYTES = 512 * 1024


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
