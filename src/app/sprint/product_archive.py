"""The product itself, as one archive a person can download, with how to run it (LR.30a).

Found in the launch review: after a run of one to three hours the page said "Finished. The results are ready below",
and the only download was the handover pack (documents, decisions and the acceptance suite) or one file at a time:
the product could not be taken away. The archive holds the workspace as the product ships - its git history
included, so its commits come with it - without dependency folders, test-runner output, or the harness's own files.
"""
from __future__ import annotations

import io
import shlex
import zipfile
from pathlib import Path

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


def files_of(repo_root: str | Path) -> list[str]:
    """The workspace-relative files the product archive holds, in order."""
    root = Path(repo_root)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        parts = relative.parts
        if not path.is_file() or path.is_symlink():
            continue
        if parts[0] in _HARNESS_OWN or any(part in _LEFT_OUT for part in parts):
            continue
        if path.name.startswith("tmp-inline-"):
            continue
        found.append(relative.as_posix())
    return found


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


def build(repo_root: str | Path, run_id: str) -> bytes:
    """The product as a zip archive under a folder named for the run, with `HOW-TO-RUN.txt` beside it."""
    root = Path(repo_root)
    buffer = io.BytesIO()
    used = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files_of(root):
            size = (root / relative).stat().st_size
            if used + size > MOST_BYTES:
                break
            archive.write(root / relative, f"{run_id}/{relative}")
            used += size
        steps = how_to_run(root)
        if steps:
            archive.writestr(f"{run_id}/HOW-TO-RUN.txt", "From this folder:\n\n" + "\n".join(steps)
                             + "\n\nThe product's README says more.\n")
    return buffer.getvalue()


__all__ = ["MOST_BYTES", "build", "files_of", "how_to_run"]
