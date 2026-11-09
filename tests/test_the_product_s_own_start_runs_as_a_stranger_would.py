"""The product's own start command is checked the way a stranger runs it: no agent home, no project virtualenv on PATH.

Measured on a custom-stack baseline: `start.sh` ran a bare `python3`; inside the sandbox the project's `.venv` is first
on every command's PATH and the agent's home holds what a bare `pip install` put there, so the service started, the
locked suite passed, and the release saw nothing wrong. The benchmark started it as delivered: `No module named
'falcon'`, hidden 0 of 9 - a false acceptance.
"""
from __future__ import annotations

import os

from app.acceptance import start_output


def test_the_start_check_runs_with_a_fresh_home_and_the_plain_path(tmp_path, monkeypatch):
    project = tmp_path / "notes-api"
    project.mkdir()
    (project / "start.sh").write_text("exec python3 app.py\n")
    seen = {}

    def execute(repo_root, argv, where, env):
        seen.update(env)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(start_output, "command_for", lambda root: (["sh", "start.sh"], "notes-api"))
    monkeypatch.setattr(start_output, "_execute", execute)
    start_output.what_it_wrote(tmp_path)

    assert "HOME" in seen and ".agent-home" not in seen["HOME"]
    assert seen.get("PATH") == os.environ.get("PATH", "")
