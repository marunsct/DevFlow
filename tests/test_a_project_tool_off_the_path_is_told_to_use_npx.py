"""A project's own tool, installed but off the PATH, is told to run through npx, not to be installed.

Measured on one run: a Hono setup declared `["vitest", "run"]`. Vitest was installed under `node_modules/.bin`; the
sandbox said it "is not installed in this environment ... or `npm install`", the setup could not see what was wrong,
and three attempts left the setup unproven.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.plugins.seed import SEED_INSTRUCTIONS, SETUP
from app.tools.sandbox import SandboxExecutor

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _run(workspace: Path, name: str = "vitest") -> dict:
    return SandboxExecutor._execute_here([name, "run"], str(workspace), "testing_specialist", "test", 10, None, "notes-api")


def test_an_installed_project_binary_is_told_to_run_through_npx(tmp_path):
    (tmp_path / "notes-api" / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "notes-api" / "node_modules" / ".bin" / "vitest").write_text("#!/bin/sh\n")

    error = _run(tmp_path)["error"]

    assert "installed in the project" in error and "npx vitest" in error and "npm test" in error
    assert "Install it" not in error


def test_a_tool_that_is_not_installed_anywhere_is_still_told_to_install_it(tmp_path):
    (tmp_path / "notes-api").mkdir()

    error = _run(tmp_path)["error"]

    assert "is not installed in this environment" in error and "npm install" in error


def test_the_javascript_setup_guidance_names_the_pitfall_without_the_banned_words():
    text = SEED_INSTRUCTIONS["typescript" + SETUP]
    bullet = text.split("- A PROJECT'S OWN TOOL IS RUN THROUGH")[1].split("\n- ")[0]

    assert 'declared `["vitest", "run"]`' in bullet and '["npx", "vitest", "run"]' in bullet
    assert not BANNED.search(bullet)
