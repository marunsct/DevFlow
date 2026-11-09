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
import os
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
    """Git's answer, each stream kept to a head and a tail (`bounded_output`); None when git failed.

    Read whole, `git diff HEAD` over a product that wrote a large file into
    its own tree held all of it in the worker's memory to make a fingerprint.
    What is left out of the middle still counts: the kept text names a digest
    of the whole stream.
    """
    from app.tools.bounded_output import run_bounded

    try:
        done = run_bounded(["git", "-C", str(root), *args], text=True, errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


#: How many untracked files the fingerprint reads; past it, a file is known by its name.
MOST_UNTRACKED_FILES = 2_000


#: Above this size a changed file is fingerprinted by its size and time, not read whole.
MOST_HASHED_BYTES = 64_000_000


def _the_blob_id(path: Path) -> str:
    """The id git gives `path`'s content as it is on disk (`git hash-object`); "?" when it cannot be read."""
    try:
        if path.is_symlink():
            data = os.readlink(path).encode()
            return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - git's own id
        size = path.stat().st_size
        if size > MOST_HASHED_BYTES:
            return f"size {size} at {path.stat().st_mtime_ns}"
        digest = hashlib.sha1(b"blob %d\0" % size)  # noqa: S324 - git's own id
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "?"


def fingerprint(repo_root: str | Path) -> str:
    """The product's files as they are on disk, as git would commit them; "" without a repository.

    The same before and after a commit of what is on disk: each file is known by its content's id, the committed
    one for a file unchanged since HEAD and the one git would give it for a changed or untracked file.
    """
    root = Path(repo_root)
    # The product's files as committed, not the commit's id: the harness commits its own records between
    # measurements, and a fingerprint that began with HEAD read an unchanged product as changed (measured: the unit
    # tests, five minutes each on a test that never settled, ran again after each such commit).
    # Nor the committed files and the diff apart: found in a code review, a kept fix measured and then committed
    # changed the fingerprint, so every measurement taken just before a commit was read as of another product - the
    # suite's and the unit tests' runs were not reused, and nothing stored could say "unchanged" after a fix.
    tree = _git(root, "ls-tree", "-r", "-z", "HEAD")
    if tree is None:
        return ""
    files: dict[str, str] = {}
    # `ls-tree` takes no exclusions: the same paths are left out here as the pathspecs leave out below.
    for entry in tree.split("\0"):
        meta, _, path = entry.partition("\t")
        if path and not _the_harness_s(path):
            files[path] = meta.split()[-1] if meta.split() else "?"
    changed = _git(root, "diff", "--name-only", "-z", "HEAD", "--", ".", *_NOT_THE_PRODUCT) or ""
    untracked = _git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", ".", *_NOT_THE_PRODUCT) or ""
    for name in sorted(name for name in changed.split("\0") if name.strip()):
        if os.path.lexists(root / name):
            files[name] = _the_blob_id(root / name)
        else:
            files.pop(name, None)
    # An untracked file by its content too, not its name alone: a new file changed again before anything committed
    # it read as unchanged, and a measurement taken before the change would stand (`measured_once`).
    for number, name in enumerate(sorted(name for name in untracked.split("\0") if name.strip())):
        files[name] = _the_blob_id(root / name) if number < MOST_UNTRACKED_FILES else "?"
    listing = "\n".join(f"{path}\0{blob}" for path, blob in sorted(files.items()))
    return hashlib.sha256(listing.encode("utf-8", "replace")).hexdigest()[:20]


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
