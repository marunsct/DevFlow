"""A read that fails identically, twice, in silence.

`read_file` sits outside the repeated-query middleware on purpose: the
workspace backend keeps a better record for it, keyed on the file's identity as
well as its bytes. But that record is only kept for reads that succeed, so a
stage could ask for a file that is not there as often as it liked.

Measured on one run's `specialist_backend_2`, whose task was to create
`app.js`: two identical `read_file` calls for `/task-manager/app.js`, two
identical `Error: File '/task-manager/app.js' not found`, and no notice of any
kind. `edit_artifact` has had this note since one run.
"""

from __future__ import annotations

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import _NoticingRepeats


@pytest.fixture(autouse=True)
def _forget():
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


@pytest.fixture()
def in_a_stage(monkeypatch):
    """Pretend to be inside a graph run, the way `stage_memory` sees one."""
    import langgraph.config

    monkeypatch.setattr(
        langgraph.config,
        "get_config",
        lambda: {"configurable": {"thread_id": "run-1:specialist_backend_2:abcd"}},
    )


def _note(backend: _NoticingRepeats, path: str, error: str) -> str:
    return backend._note_if_it_failed_this_way_before(path, error)


def test_the_first_failure_says_nothing_extra():
    """One look is ordinary while a stage works out what to build."""
    backend = _NoticingRepeats()

    assert _note(backend, "/task-manager/app.js", "not found") == ""


def test_the_second_identical_failure_says_so():
    backend = _NoticingRepeats()
    _note(backend, "/task-manager/app.js", "not found")

    note = _note(backend, "/task-manager/app.js", "not found")

    assert "failed the same way" in note
    assert "will fail again" in note


def test_it_says_what_to_do_instead():
    backend = _NoticingRepeats()
    _note(backend, "/task-manager/app.js", "not found")

    note = _note(backend, "/task-manager/app.js", "not found")

    assert "Create it, or carry on without it" in note


def test_a_different_failure_at_the_same_path_is_new_information():
    backend = _NoticingRepeats()
    _note(backend, "/task-manager/app.js", "not found")

    assert _note(backend, "/task-manager/app.js", "permission denied") == ""


def test_a_different_path_is_counted_on_its_own():
    backend = _NoticingRepeats()
    _note(backend, "/task-manager/app.js", "not found")

    assert _note(backend, "/task-manager/style.css", "not found") == ""


def test_the_count_survives_a_rebuilt_backend(in_a_stage):
    """The backend is rebuilt with the agent on every approval resume.

    The count lives in `stage_memory`, keyed on the running stage, for exactly
    this reason - a stage that writes a file between two reads is a stage doing
    its job, and it would otherwise start counting from zero each time.
    """
    _note(_NoticingRepeats(), "/task-manager/app.js", "not found")

    note = _note(_NoticingRepeats(), "/task-manager/app.js", "not found")

    assert "failed the same way" in note


def test_outside_a_graph_run_each_backend_keeps_its_own_count():
    """No stage to key on, so the instance dict is the store - as designed."""
    _note(_NoticingRepeats(), "/task-manager/app.js", "not found")

    assert _note(_NoticingRepeats(), "/task-manager/app.js", "not found") == ""
