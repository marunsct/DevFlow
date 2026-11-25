"""A builder's memory holds the files its work order names and what they import, and the harness's own files last
(LF.1468).

Measured on one medium run: a backend builder opened on a memory chosen by path - the harness's 24,905-character
`playwright.setup.mjs` held, the product's `schemas.py` (the earlier builder's file it builds against) and the due
acceptance tests not - and read `schemas.py` 9 times. The workspace, the request and the budget here are that
opening's, rebuilt from the transcript.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.agents import project_memory

CAPTURED = json.loads(
    (Path(__file__).parent / "captured" / "backend_builder_opening_workspace.json").read_text("utf-8"))
PROJECT = "task-management-dashboard/"


def _workspace(tmp_path) -> Path:
    for path, text in CAPTURED["files"].items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    return tmp_path


def _held(tmp_path, monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("CANONICAL_MEMORY", "on")
    # As the builder's memory was rendered: on the product's code, its other files outlined.
    _, held = project_memory.render(_workspace(tmp_path), CAPTURED["budget"], CAPTURED["opening_request"],
                                    on_code=True, outlined=True)
    return held


def test_the_files_the_work_builds_on_are_held(tmp_path, monkeypatch):
    held = _held(tmp_path, monkeypatch)

    assert PROJECT + "task_management_dashboard/schemas.py" in held
    assert PROJECT + "acceptance/auth.spec.js" in held


def test_the_harness_s_own_files_come_after_the_product_s(tmp_path, monkeypatch):
    held = _held(tmp_path, monkeypatch)

    assert PROJECT + "playwright.setup.mjs" not in held
    # The product's own files are held.
    assert PROJECT + "task_management_dashboard/models.py" in held
