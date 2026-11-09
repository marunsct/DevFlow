"""A relative program missing where a command runs, but present in a project folder, is named there - not "install it".

Measured on one run: a fixer ran `./.venv/bin/python -m pytest` from the workspace root; the virtualenv was the
project's (`textkit/.venv`), and the refusal said to create a virtualenv and install.
"""
from __future__ import annotations

import os

from app.tools.sandbox import SandboxExecutor


def _workspace(tmp_path):
    python = tmp_path / "textkit" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    return tmp_path


def test_the_project_s_venv_is_named_with_the_folder_to_run_from(tmp_path):
    out = SandboxExecutor._execute_here(["./.venv/bin/python", "-m", "pytest"], str(_workspace(tmp_path)),
                                        "backend_specialist", "test", 30, None)
    assert "textkit/.venv/bin/python" in out["error"] and "`working_directory` set to `textkit`" in out["error"]
    assert "Nothing needs installing" in out["error"]


def test_a_program_found_nowhere_is_still_to_be_installed(tmp_path):
    out = SandboxExecutor._execute_here(["./.venv/bin/ruff", "check"], str(_workspace(tmp_path)),
                                        "backend_specialist", "test", 30, None)
    assert "is not installed in this environment" in out["error"]
