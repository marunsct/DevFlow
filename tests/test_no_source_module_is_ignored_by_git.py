"""No module under `src/` is one git ignores.

A deploy builds the image from the commit, so a module `.gitignore` matches is
on the developer's disk, passes every local test, and is missing from the
running worker. Measured while building one: `.gitignore`'s `fix_*.py` matched
a new `src/app/graph/fix_cycle.py`, and nothing said so.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_every_source_module_is_one_git_tracks_or_can():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    ignored = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "src"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    modules = [path for path in ignored if path.endswith(".py") and "__pycache__" not in path]
    assert not modules, f"git ignores these source modules: {modules}"
