"""A run started from a finished run's product, with a change brief (plan BW.2, behind `CHANGE_REQUEST_RUNS`).

A change to a delivered product had to go through an upload: download the
workspace, archive it, upload it, start a run from the archive. With the
switch on, `POST /runs/{id}/start` takes `{"source": {"type": "run",
"run_id": ...}}` naming a completed run of the same tenant; its product is
copied into the new workspace with its history, and the new run is a seeded
run like any other - BW.1's contract holds the product's own green tests,
the old acceptance tests are files of the product, and the brief is the
change.

Left behind: the harness's records of the old run (`.harness`, whose locked
suite and contract belong to that run) and what installs and test runs make,
which the new run makes again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.switches import is_on

#: `CHANGE_REQUEST_RUNS` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Directories never copied: the old run's records, and what installs and test runs make.
LEFT_BEHIND = frozenset({
    ".harness", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "test-results", "playwright-report", ".next", ".turbo", "target", ".gradle",
})


def enabled() -> bool:
    return is_on("CHANGE_REQUEST_RUNS", ON_BY_DEFAULT)


def _head(root: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, errors="replace", timeout=30)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


#: Folders a toolchain generates, each known by what sits beside or inside it.
_GENERATED_BESIDE = {"target": ("Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts")}
_GENERATED_INSIDE = {"venv": ("pyvenv.cfg",), ".venv": ("pyvenv.cfg",)}
_ALWAYS_GENERATED = {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _generated_or_outside(finished: Path):
    """An `ignore` for `copytree`: below the top, only folders proven generated, and any link that leaves the workspace.

    `ignore_patterns` applied the whole top-level set at every depth, so a
    product's own `src/target/` or `src/venv/` was left out of the copy; and
    a nested symlink to a file outside the workspace was copied as a link.
    """
    root = os.path.realpath(finished)

    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped: set[str] = set()
        here = Path(directory)
        for name in names:
            path = here / name
            if path.is_symlink() and not os.path.realpath(path).startswith(root + os.sep):
                skipped.add(name)
            elif name in _ALWAYS_GENERATED:
                skipped.add(name)
            elif name in _GENERATED_BESIDE and any((here / marker).exists() for marker in _GENERATED_BESIDE[name]):
                skipped.add(name)
            elif name in _GENERATED_INSIDE and any((path / marker).exists() for marker in _GENERATED_INSIDE[name]):
                skipped.add(name)
        return skipped

    return ignore


def seed_from_run(workspace: Path, finished: Path, run_id: str) -> dict[str, str]:
    """Copy a finished run's product into `workspace`; the provenance to record."""
    from app.server.seeding import SeedError, _enforce_size

    if not enabled():
        raise SeedError("Starting a run from a finished run's product is switched off (CHANGE_REQUEST_RUNS).")
    if not finished.is_dir():
        raise SeedError("That run's workspace is no longer there.")
    copied: list[Path] = []
    try:
        for entry in finished.iterdir():
            if entry.name in LEFT_BEHIND or entry.is_symlink():
                continue
            target = workspace / entry.name
            copied.append(target)
            if entry.is_dir():
                shutil.copytree(entry, target, symlinks=True, ignore=_generated_or_outside(finished), dirs_exist_ok=True)
            else:
                shutil.copy2(entry, target)
    except (OSError, shutil.Error) as error:
        # Left half-copied, the workspace blocked every retry with what was there.
        for target in copied:
            shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink(missing_ok=True)
        raise SeedError(f"Could not copy that run's product: {str(error)[:200]}") from error
    _enforce_size(workspace, "That run's product")
    return {"type": "run", "run_id": run_id, "commit": _head(workspace)}


__all__ = ["LEFT_BEHIND", "ON_BY_DEFAULT", "enabled", "seed_from_run"]
