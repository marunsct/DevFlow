"""A test command run again with nothing changed is answered from its last result, not run again.

Measured on one run's acceptance suite writer: the suite's own command was run three times in four minutes, the
second two seconds after the first result with nothing written between and the third after four reads. Each took
about 64 seconds and gave the same 0 of 37. The result already said "no file has changed since" - after paying for
the run. The guard that withholds a repeat only does so after three identical passes, so a failing suite never met it.

The container run (`SandboxExecutor._run`) is the edge stood in for: each test counts how many times it was reached.
"""

from __future__ import annotations

import os
import time

import pytest

from app.tools.repository import run_approved_validation
from app.tools.sandbox import SandboxExecutor, read_execution_ledger

SUITE = ["npm", "run", "test:acceptance"]
FAILING = "# tests 37\n# pass 0\n# fail 37\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A project whose suite fails 0 of 37, with every container run counted."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text('{"name": "app"}\n')
    (tmp_path / "app" / "server.js").write_text("module.exports = 1;\n")
    ran: list[list[str]] = []

    def fails(cls, command, *args, **kwargs):
        ran.append(list(command))
        return {"returncode": "1", "stdout": FAILING, "stderr": "Error: expected 200, got 404\n"}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(fails))
    return tmp_path, ran


def _run_the_suite(root, command=SUITE, category="test"):
    return SandboxExecutor.execute(command, str(root), "testing_specialist", category, working_directory="app")


def _later(path):
    moment = time.time() + 60
    os.utime(path, (moment, moment))


def test_an_identical_rerun_with_nothing_changed_is_not_run_and_returns_the_earlier_result_marked(workspace):
    root, ran = workspace
    _run_the_suite(root)

    again = _run_the_suite(root)

    assert len(ran) == 1, "the repeat is answered, not run"
    assert again["returncode"] == "1" and FAILING in again["stdout"] and "got 404" in again["stderr"], (
        "the earlier result itself: exit code, output and error")
    assert again["stdout"].startswith("[Not run again:"), "marked as the earlier result, before the output"
    assert "0 of 37 passed" in again["stdout"] and "no file has changed since" in again["stdout"]


def test_the_validation_tool_returns_the_earlier_result_marked(workspace):
    """`run_validation` is the tool the suite writers use; its reply carries the mark in its output."""
    root, ran = workspace
    run_approved_validation(str(root), SUITE, "app")

    again = run_approved_validation(str(root), SUITE, "app")

    assert len(ran) == 1
    assert again["returncode"] == 1 and again["stdout"].startswith("[Not run again:")


def test_a_rerun_answered_from_the_earlier_result_is_in_the_ledger_with_the_time_it_saved(workspace):
    root, _ = workspace
    _run_the_suite(root)
    first = read_execution_ledger(str(root))[-1]

    _run_the_suite(root)

    repeat = read_execution_ledger(str(root))[-1]
    assert repeat["reused_from"] == first["at"] and repeat["saved_seconds"] == first["duration_seconds"]
    assert (repeat["passed"], repeat["failed"], repeat["tests"]) == (0, 37, 37) and repeat["returncode"] == 1


def test_a_third_unchanged_run_is_answered_from_the_same_result(workspace):
    root, ran = workspace
    for _ in range(3):
        _run_the_suite(root)

    assert len(ran) == 1


def test_after_a_file_changes_the_command_runs(workspace):
    root, ran = workspace
    _run_the_suite(root)
    (root / "app" / "server.js").write_text("module.exports = 2;\n")
    _later(root / "app" / "server.js")

    again = _run_the_suite(root)

    assert len(ran) == 2 and not again["stdout"].startswith("[Not run again:")


@pytest.mark.parametrize("change", ["a deleted file", "a new dotfile"])
def test_a_change_no_modification_time_shows_still_runs_it(workspace, change):
    root, ran = workspace
    _run_the_suite(root)
    if change == "a deleted file":
        (root / "app" / "server.js").unlink()
    else:
        (root / "app" / ".babelrc").write_text("{}\n")

    _run_the_suite(root)

    assert len(ran) == 2


def test_the_harness_s_own_records_are_not_a_change(workspace):
    root, ran = workspace
    _run_the_suite(root)
    (root / ".harness").mkdir()
    (root / ".harness" / "acceptance-result.json").write_text("{}\n")
    (root / ".project-memory.json").write_text("{}\n")
    (root / "app" / "test-results").mkdir()
    (root / "app" / "test-results" / ".last-run.json").write_text("{}\n")

    _run_the_suite(root)

    assert len(ran) == 1


def test_any_command_recorded_in_between_makes_it_run(workspace):
    """An install can change what a test sees without changing a file of the work."""
    root, ran = workspace
    _run_the_suite(root)
    SandboxExecutor.execute(["npx", "playwright", "install", "chromium"], str(root), "testing_specialist",
                            "install", working_directory="app")

    _run_the_suite(root)

    assert ran.count(SUITE) == 2


def test_an_install_command_is_never_answered_from_an_earlier_result(workspace):
    root, ran = workspace
    for _ in range(2):
        SandboxExecutor.execute(["npm", "install"], str(root), "testing_specialist", "install",
                                working_directory="app")

    assert len(ran) == 2


def test_a_command_outside_the_test_category_is_never_answered_from_an_earlier_result(workspace):
    root, ran = workspace
    for _ in range(2):
        _run_the_suite(root, ["node", "scripts/check.js"], "build")

    assert len(ran) == 2


def test_when_the_workspace_cannot_be_read_the_command_runs(workspace):
    """Unknown is never taken for unchanged."""
    root, ran = workspace
    hidden = root / "app" / "private"
    hidden.mkdir()
    hidden.chmod(0)
    try:
        for _ in range(2):
            _run_the_suite(root)
    finally:
        hidden.chmod(0o755)

    assert len(ran) == 2


def test_a_run_that_changed_the_workspace_while_it_ran_is_not_reused(tmp_path, monkeypatch):
    """A file written during the run - by the command or by another stage - may not be in the result it gave."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "server.js").write_text("module.exports = 1;\n")
    ran: list[int] = []

    def writes_while_it_runs(cls, command, *args, **kwargs):
        ran.append(1)
        (tmp_path / "app" / "data.db").write_bytes(b"x" * len(ran))
        return {"returncode": "1", "stdout": FAILING, "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(writes_while_it_runs))
    for _ in range(2):
        _run_the_suite(tmp_path)

    assert len(ran) == 2


def test_the_mark_a_model_reads_has_none_of_the_banned_words(workspace):
    import re

    root, _ = workspace
    _run_the_suite(root)
    failed_again = _run_the_suite(root)["stdout"]
    mark = failed_again.split("]", 1)[0]
    assert mark.startswith("[Not run again:")

    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", mark, re.I), word


def test_the_mark_after_a_pass_has_none_of_the_banned_words(tmp_path, monkeypatch):
    import re

    (tmp_path / "app").mkdir()
    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(
        lambda cls, *a, **k: {"returncode": "0", "stdout": "# tests 3\n# pass 3\n# fail 0\n", "stderr": ""}))
    _run_the_suite(tmp_path)
    mark = _run_the_suite(tmp_path)["stdout"].split("]", 1)[0]

    assert mark.startswith("[Not run again:") and "3 of 3 passed" in mark
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", mark, re.I), word
