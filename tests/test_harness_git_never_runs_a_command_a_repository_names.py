"""Harness git commands never run a command a repository's own config or hooks name.

Found in the launch review: an uploaded archive keeps its `.git`, and `git status` on it in the server (and git diff
in the worker) ran with the repository's config, so `core.fsmonitor` or a diff driver could run any command with the
server's secrets in its environment.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.tools import version_control

SRC = Path(__file__).resolve().parent.parent / "src" / "app"


def test_every_harness_git_command_starts_with_the_safe_settings():
    raw = []
    for path in SRC.rglob("*.py"):
        if path.name == "sandbox.py":
            continue  # the agents' own commands, which the sandbox runs
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'\[\s*"git"\s*,', line):
                raw.append(f"{path.relative_to(SRC)}:{number}")
    assert raw == []
    assert "core.fsmonitor=false" in version_control.git_safely()
    assert "core.hooksPath=/dev/null" in version_control.git_safely()


def test_a_monitor_a_repository_names_does_not_run(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    marker = tmp_path / "ran"
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.fsmonitor", f"touch {marker}; false"], check=True)
    version_control._git(tmp_path, "status", "--porcelain")
    assert not marker.exists()


def test_a_seeded_repository_loses_its_command_settings_and_hooks_but_keeps_its_remote(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    git = tmp_path / ".git"
    (git / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n\tfsmonitor = sh evil.sh\n\tpager = sh evil.sh\n"
        '[filter "x"]\n\tsmudge = sh evil.sh\n[alias]\n\tst = !sh evil.sh\n'
        '[remote "origin"]\n\turl = https://example.com/r.git\n')
    (git / "hooks" / "post-checkout").write_text("#!/bin/sh\nsh evil.sh\n")
    assert version_control.make_safe(tmp_path) is True
    config = (git / "config").read_text()
    assert "evil" not in config and "repositoryformatversion" in config and "https://example.com/r.git" in config
    assert not (git / "hooks" / "post-checkout").exists()
