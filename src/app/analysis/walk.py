"""Walk a workspace without entering the directories nobody reads.

Every check that looked for files did `root.rglob(...)` and threw away what was
under `node_modules`, `.venv`, `.git` and the rest afterwards. The filter was
right and the walk was not: it still entered every one of those directories and
stat-ed every file in them, on every check, on every round. A workspace from one
run held 1,744 files of which 1,310 were in `node_modules`; a project with a
Python virtual environment holds tens of thousands.

Pointed at `/`, the same `rglob` descended into the whole machine and the
process died with a segmentation fault in the walk itself - which is how a unit
test that passed `/` as a repository root took the full suite down with it.

So the directories are pruned before they are entered, symlinked directories
are not followed (a link back to an ancestor never ends), and a directory that
cannot be read is skipped rather than raising.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from pathlib import Path


def _walk(root: Path, skip: Iterable[str], skip_hidden: bool = False) -> Iterator[tuple[Path, list[str], list[str]]]:
    skipped = set(skip)
    for directory, subdirectories, files in os.walk(root, followlinks=False, onerror=lambda _: None):
        # Pruned in place: `os.walk` does not descend into what is removed here.
        subdirectories[:] = sorted(
            d for d in subdirectories if d not in skipped and not (skip_hidden and d.startswith("."))
        )
        yield Path(directory), subdirectories, sorted(files)


def files_under(root: str | Path, skip: Iterable[str] = (), name: str = "*", *, skip_hidden: bool = False) -> Iterator[Path]:
    """Every file under `root` whose basename matches `name`, outside `skip`.

    `skip` names directories, matched against each directory's own name at any
    depth - the same test the callers applied to `path.parts` afterwards.
    `skip_hidden` leaves out every directory whose name starts with a dot too.
    """
    for directory, _, files in _walk(Path(root), skip, skip_hidden):
        for file_name in files:
            if name == "*" or fnmatch.fnmatchcase(file_name, name):
                yield directory / file_name


def directories_under(root: str | Path, skip: Iterable[str] = (), name: str = "*") -> Iterator[Path]:
    """Every directory under `root` whose name matches `name`, outside `skip`."""
    for directory, subdirectories, _ in _walk(Path(root), skip):
        for sub in subdirectories:
            if name == "*" or fnmatch.fnmatchcase(sub, name):
                yield directory / sub


__all__ = ["directories_under", "files_under"]
