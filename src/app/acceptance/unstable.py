"""A criterion whose tests fail in the whole suite and pass alone on the same product is unstable, not fixed.

At dispatch a defect's own tests are re-measured alone, and a pass closes it
(Initiative L.3) - right when an earlier fix resolved it. When nothing has
changed since the round measured it failing, the only difference is that the
tests ran alone: they depend on the order they run in, or on data another
test leaves behind. Measured on a gate run: across three attempts at one
sprint, criteria the round raised were closed at dispatch by a passing
re-measure and raised again by the next round on the same product, fixers
were sent at them, and the sprint failed twice.

The suite's saved result carries a fingerprint of the product it measured;
the dispatch compares it with the product now.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

#: Paths whose changes are the harness's or a runner's, never the product's.
_NOT_THE_PRODUCT = (":(exclude,glob).harness/**", ":(exclude,glob)**/test-results/**",
                    ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)docs/**")


def _the_harness_s(path: str) -> bool:
    """Whether `path` is one `_NOT_THE_PRODUCT` leaves out: the harness's records, test results, caches."""
    parts = path.split("/")
    return parts[0] in (".harness", "docs") or "test-results" in parts[:-1] or "__pycache__" in parts[:-1]


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


#: Bounds on reading untracked files for the fingerprint.
MOST_UNTRACKED_FILES = 2_000
MOST_UNTRACKED_BYTES = 1_000_000


def fingerprint(repo_root: str | Path) -> str:
    """The product's state as git sees it - its commit and its uncommitted changes; "" without a repository."""
    root = Path(repo_root)
    # The product's files as committed, not the commit's id: the harness commits its own records between
    # measurements, and a fingerprint that began with HEAD read an unchanged product as changed (measured: the unit
    # tests, five minutes each on a test that never settled, ran again after each such commit).
    tree = _git(root, "ls-tree", "-r", "HEAD")
    if tree is None:
        return ""
    # `ls-tree` takes no exclusions: the same paths are left out here as the pathspecs leave out below.
    head = "\n".join(line for line in tree.splitlines()
                     if not _the_harness_s(line.split("\t", 1)[-1] if "\t" in line else line))
    diff = _git(root, "diff", "HEAD", "--", ".", *_NOT_THE_PRODUCT) or ""
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", ".", *_NOT_THE_PRODUCT) or ""
    # An untracked file by its content too, not its name alone: a new file changed again before anything committed
    # it read as unchanged, and a measurement taken before the change would stand (`measured_once`).
    contents = hashlib.sha256()
    for name in sorted(line for line in untracked.splitlines() if line.strip())[:MOST_UNTRACKED_FILES]:
        try:
            contents.update(name.encode() + b"\0" + (root / name).read_bytes()[:MOST_UNTRACKED_BYTES])
        except OSError:
            contents.update(name.encode() + b"\0?")
    return hashlib.sha256(f"{head.strip()}\n{diff}\n{untracked}\n{contents.hexdigest()}".encode()).hexdigest()[:20]


def unchanged_since_the_suite_measured(repo_root: str | Path) -> bool:
    """Whether the product is exactly as it was when the suite last measured it."""
    from app.acceptance import suite

    measured = str((suite.last_result(repo_root) or {}).get("fingerprint") or "")
    return bool(measured) and measured == fingerprint(repo_root)


def reason(criteria: list[str]) -> str:
    """What the dispute is told about an unstable criterion."""
    named = ", ".join(criteria) or "this criterion"
    return (f"The tests of {named} fail when the whole suite runs and pass when they run alone, on the same "
            "product with nothing changed in between: they depend on the order the tests run in, or on data "
            "another test leaves behind. A fix to the product cannot settle that; the tests must each create "
            "what they read and not rely on what ran before them.")


__all__ = ["fingerprint", "reason", "unchanged_since_the_suite_measured"]
