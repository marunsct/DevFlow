"""A restarted stage is told why its last attempt ended, which files it was refused, and which it changed.

Measured on one run: a unit-test stage found a crash in a file another work order owns, was refused it, and spent the
rest of its forty calls building a child-process runner around the product's module state. The next attempt was told
only the commands it had run, read the half-built runner, and started down the same road.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.agents import stage_memory
from app.agents.carry_over import carry_over_note
from app.analysis import project_memory
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def clean_memory():
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


def test_the_refusals_the_changes_and_the_reason_are_carried(tmp_path):
    stage_memory._MEMORY[("t1", "files_refused_as_another_work_order_s")] = {"notes-api/src/app.ts": 1}
    project_memory.record(tmp_path, "notes-api/test/storage.test.ts", "specialist_testing_1")
    project_memory.record(tmp_path, "notes-api/test/runner.mjs", "specialist_testing_1")
    project_memory.record(tmp_path, "notes-api/src/app.ts", "specialist_backend_0")

    note = carry_over_note("t1", str(tmp_path), "specialist_testing_1", "produced no structured response")

    assert "It ended because it produced no structured response" in note
    assert "another work order owns them: notes-api/src/app.ts" in note and "`blockers`" in note
    changed = note[note.index("Files it changed"):]
    assert "notes-api/test/storage.test.ts" in changed and "notes-api/test/runner.mjs" in changed
    assert "specialist_backend_0" not in note and "notes-api/src/app.ts" not in changed.split(".")[0]
    assert not BANNED.search(note)


def test_a_refusal_alone_is_worth_a_note(tmp_path):
    stage_memory._MEMORY[("t2", "files_refused_as_another_work_order_s")] = {"src/a.py": 2}
    assert "src/a.py" in carry_over_note("t2", str(tmp_path))


def test_the_restart_passes_its_stage_and_reason():
    assert "carry_over_note(inner_thread_id, repo_root, stage_name, why)" in inspect.getsource(
        workflow._restart_on_a_fresh_conversation)
