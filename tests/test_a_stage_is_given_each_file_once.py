"""A stage's opening request carries each project file once: the project memory, not the memory and a snapshot.

Measured on a Measure run: every call of a fix stage carried 14 files twice,
about 24,000 characters, and the snapshot called a file "not included, read
it" that the memory held and refused to let the stage read.
"""
from __future__ import annotations

import inspect
import os
from unittest import mock

from app.agents import project_snapshot
from app.graph import workflow


def _workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("items-api")
    (tmp_path / "items-api").mkdir()
    (tmp_path / "items-api" / "store.py").write_text("def load():\n    return []\n")
    return tmp_path


def test_under_the_project_memory_the_snapshot_is_not_given_again(tmp_path):
    root = _workspace(tmp_path)
    with mock.patch.dict(os.environ, {"PROJECT_MEMORY": ""}):
        assert project_snapshot.for_a_stage(root) == ""
    with mock.patch.dict(os.environ, {"PROJECT_MEMORY": "off"}):
        assert "items-api/store.py" in project_snapshot.for_a_stage(root)


def test_an_empty_project_is_still_said_to_be_empty(tmp_path):
    (tmp_path / ".project-directory").write_text("items-api")
    (tmp_path / "items-api").mkdir()
    with mock.patch.dict(os.environ, {"PROJECT_MEMORY": ""}):
        assert "has no files yet" in project_snapshot.for_a_stage(tmp_path)


def test_the_stage_runner_asks_for_what_a_stage_is_given():
    source = inspect.getsource(workflow._run_gated_agent)
    assert "for_a_stage(" in source and "project_snapshot(" not in source
