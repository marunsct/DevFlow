"""What a run changed, read from its workspace's own history (UI plan: the diff viewer).

Every stage's work is committed in the run's workspace - "Before defect_fix_2_3",
"Fix: [AC-12] ..." - so the history is already there. This only reads it: the
list of commits with the files each touched, and one commit's diff, capped.
Read-only git commands with a fixed argument list; a commit is named by its
hash and nothing else reaches the command line.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

#: Commits listed at most, newest first.
MOST_COMMITS = 200
#: Characters of one diff returned at most.
MOST_DIFF_CHARS = 200_000

_A_HASH = re.compile(r"^[0-9a-f]{7,40}$")
_SEPARATOR = "\x1f"


class ChangesUnavailable(ValueError):
    """The workspace has no history to read, or the commit is not one of it."""


class ChangesTookTooLong(ChangesUnavailable):
    """Reading the history did not finish in time."""


def _git(root: Path, *args: str) -> str:
    if not (root / ".git").exists():
        raise ChangesUnavailable("This run's workspace keeps no history.")
    try:
        done = subprocess.run(
            # No textconv and no external diff: a filter the workspace's own
            # configuration names would run a command it chose (Initiative AO.8).
            ["git", "-C", str(root), "-c", "core.quotepath=off", "-c", "core.fsmonitor=false", *args],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ChangesTookTooLong("Reading this run's history took too long.") from error
    if done.returncode != 0:
        raise ChangesUnavailable((done.stderr or "git failed").strip()[:200])
    return done.stdout


def commits(root: str | Path, limit: int = MOST_COMMITS) -> list[dict[str, Any]]:
    """The workspace's commits, newest first: hash, message, time, and each file's lines added and removed."""
    out = _git(
        Path(root), "log", f"--max-count={int(limit)}", "--numstat", "--no-ext-diff",
        f"--format=%x1e%H{_SEPARATOR}%s{_SEPARATOR}%cI",
    )
    found: list[dict[str, Any]] = []
    for block in out.split("\x1e"):
        lines = [line for line in block.strip("\n").splitlines() if line.strip()]
        if not lines:
            continue
        sha, subject, at = (lines[0].split(_SEPARATOR) + ["", ""])[:3]
        files = []
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) == 3:
                added, removed, path = parts
                files.append({
                    "path": path,
                    "added": int(added) if added.isdigit() else None,
                    "removed": int(removed) if removed.isdigit() else None,
                })
        found.append({"sha": sha, "message": subject, "at": at, "files": files})
    return found


def document_diff(root: str | Path, path: str) -> dict[str, Any]:
    """One file's change since its newest committed version that differs from it now (plan BG.3).

    A review pauses with the revised document on disk, committed or not; the
    version before is the newest commit whose copy differs from it. The path
    is taken literally, never as a pattern.
    """
    nothing = {"path": path, "since": None, "since_at": None, "diff": "", "truncated": False}
    # `git log` fails on a history with no commit yet; that is no earlier version, not an error.
    if not _git(Path(root), "rev-list", "--max-count=1", "--all").strip():
        return nothing
    found = _git(Path(root), "--literal-pathspecs", "log", "--max-count=10", f"--format=%H{_SEPARATOR}%cI", "--", path)
    for line in found.splitlines():
        sha, _, at = line.partition(_SEPARATOR)
        if not _A_HASH.match(sha):
            continue
        text = _git(Path(root), "--literal-pathspecs", "diff", "--no-color", "--no-textconv", "--no-ext-diff", sha, "--", path)
        if text.strip():
            return {"path": path, "since": sha, "since_at": at, "diff": text[:MOST_DIFF_CHARS], "truncated": len(text) > MOST_DIFF_CHARS}
    return nothing


def diff(root: str | Path, sha: str) -> dict[str, Any]:
    """One commit's unified diff against its parent, capped; the first commit against nothing."""
    if not _A_HASH.match(str(sha or "")):
        raise ChangesUnavailable("A commit is named by its hash.")
    text = _git(Path(root), "show", "--format=", "--no-color", "--patch", "--find-renames", "--no-textconv", "--no-ext-diff", sha)
    truncated = len(text) > MOST_DIFF_CHARS
    return {"sha": sha, "diff": text[:MOST_DIFF_CHARS], "truncated": truncated}
