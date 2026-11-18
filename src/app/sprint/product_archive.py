"""The product itself, as one archive a person can download, with how to run it (LR.30a).

Found in the launch review: after a run of one to three hours the page said "Finished. The results are ready below",
and the only download was the handover pack (documents, decisions and the acceptance suite) or one file at a time:
the product could not be taken away. The archive holds the workspace as the product ships - its git history
included, so its commits come with it - without dependency folders, test-runner output, or the harness's own files.
"""
from __future__ import annotations

import io
import shlex
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

#: The most one archive may hold, uncompressed.
MOST_BYTES = 300 * 1024 * 1024
#: Folders left out wherever they are: dependencies and build caches a person installs or rebuilds.
_LEFT_OUT = frozenset({
    "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "target",
    "test-results", "playwright-report", "blob-report", "coverage", ".nyc_output", "htmlcov", ".turbo",
    ".parcel-cache", ".vite", ".cache",
})
#: The harness's own folders at the workspace root: how it worked, not what it built.
_HARNESS_OWN = frozenset({".harness", ".agent-home"})


def _shipped(relative: Path) -> bool:
    """Whether a workspace-relative path belongs in the product archive."""
    parts = relative.parts
    if not parts or parts[0] in _HARNESS_OWN or any(part in _LEFT_OUT for part in parts):
        return False
    return not relative.name.startswith("tmp-inline-")


def files_of(repo_root: str | Path) -> list[str]:
    """The workspace-relative files the product archive holds, in order."""
    root = Path(repo_root)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink() or not _shipped(relative):
            continue
        found.append(relative.as_posix())
    return found


def _criteria(root: Path) -> tuple[int | None, int | None]:
    """The criteria passing and the criteria there are in the last measurement; (None, None) before one."""
    try:
        from app.acceptance import suite

        criteria = (suite.last_result(root) or {}).get("criteria") or {}
    except Exception:  # noqa: BLE001 - the download is offered without the count
        return None, None
    if not criteria:
        return None, None
    return sum(1 for c in criteria.values() if (c or {}).get("status") == "passed"), len(criteria)


def what_it_holds(repo_root: str | Path, *, finished: bool) -> dict[str, Any]:
    """Which product the download holds and what it was measured to pass (deep review 2026-11-18, F4a).

    A finished run's download is the product as it stands. A run that did not finish (stopped, cancelled) offers its
    best attempt: the product as it stands when that is its best, or the files of the best commit when the record of
    the best attempt (`app.graph.best_attempt`) passed more acceptance tests than the product does now. `version` is
    "latest" or "best"; `commit` names the best commit only when the download is built from it.
    """
    root = Path(repo_root)
    passed, total = _criteria(root)
    said: dict[str, Any] = {"version": "latest", "commit": "", "criteria_passed": passed, "criteria_total": total,
                            "tests_passed": None, "tests_total": None}
    if finished:
        return said
    said["version"] = "best"
    try:
        from app.graph import best_attempt

        best = best_attempt.better_than_now(root)
    except Exception:  # noqa: BLE001 - the product as it stands
        best = {}
    if best:
        # The record counts acceptance tests, not criteria: the criteria of that commit were never kept.
        said.update(commit=str(best["commit"]), criteria_passed=None, criteria_total=None,
                    tests_passed=int(best.get("passed") or 0), tests_total=int(best.get("tests") or 0) or None)
    return said


def _files_at(root: Path, commit: str, into: zipfile.ZipFile, prefix: str) -> bool:
    """Write the product's files as they were at `commit` into the archive; False when git cannot give them."""
    from app import ci

    with tempfile.TemporaryDirectory(prefix="best-attempt-") as scratch:
        tar_path = Path(scratch) / "best.tar"
        made = ci._git(root, "archive", "--format=tar", "-o", str(tar_path), commit)
        if made is None or made.returncode != 0 or not tar_path.is_file():
            return False
        used = 0
        with tarfile.open(tar_path) as tar:
            for member in tar.getmembers():
                if not member.isfile() or not _shipped(Path(member.name)):
                    continue
                if used + member.size > MOST_BYTES:
                    break
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                into.writestr(f"{prefix}/{member.name}", handle.read())
                used += member.size
    return True


def how_to_run(repo_root: str | Path) -> list[str]:
    """The commands that install, test and start the product, from the stack it was built on; [] when unknown."""
    root = Path(repo_root)
    lines: list[str] = []
    try:
        from app.stacks import contract
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(root) or ""
        found = contract.the_pack(root)
        where = root / project if project else root
        if project:
            lines.append(f"cd {project}")
        if found:
            pack = found[0]
            lines += [shlex.join(step) for step in pack.install or ()]
            if pack.unit_test:
                lines.append(shlex.join(pack.unit_test))
        if (where / "start.sh").is_file():
            lines.append("sh start.sh")
    except Exception:  # noqa: BLE001 - the archive without the commands
        return []
    return lines


def build(repo_root: str | Path, run_id: str, *, at_commit: str = "") -> bytes:
    """The product as a zip archive under a folder named for the run, with `HOW-TO-RUN.txt` beside it.

    With `at_commit` (a best attempt better than the product now), the files are those of that commit, without the
    git history; if git cannot give them, the product as it stands.
    """
    root = Path(repo_root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        from_the_best = bool(at_commit) and _files_at(root, at_commit, archive, run_id)
        if not from_the_best:
            used = 0
            for relative in files_of(root):
                size = (root / relative).stat().st_size
                if used + size > MOST_BYTES:
                    break
                archive.write(root / relative, f"{run_id}/{relative}")
                used += size
        steps = how_to_run(root)
        note = (f"These are the product's files at its best attempt (commit {at_commit}), not as the run left "
                "them; the git history is not included.\n\n") if from_the_best else ""
        if steps or note:
            archive.writestr(f"{run_id}/HOW-TO-RUN.txt", note + ("From this folder:\n\n" + "\n".join(steps)
                             + "\n\nThe product's README says more.\n" if steps else ""))
    return buffer.getvalue()


__all__ = ["MOST_BYTES", "build", "files_of", "how_to_run", "what_it_holds"]
