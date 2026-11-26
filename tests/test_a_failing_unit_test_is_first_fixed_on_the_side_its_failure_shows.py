"""The first fix of a failing unit test chooses its side from the failure (PA.15, behind `UNIT_TEST_FIX_BY_FAILURE`).

Measured over the ledger (per-agent audit 2026-11-25): 44 failing unit tests beside a green suite were first worked
tests-only and 1 was fixed by that attempt. Some failures put the cause in the product themselves: an exception raised
in a product module before any assertion, a product file that does not compile. With the switch on, such a first
attempt may change the product at once and is told where the error is raised; an assertion that fails, a stand-in, or
an error located only in test files stays tests-only, as the owner's rule says. Every failure here is a captured one.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import unit_failure_side
from app.graph import defect_fix_modes
from app.sprint import Defect, RemediationCycle
from app.tools import tests_only_writes

CAPTURED = Path(__file__).parent / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RUN, STAGE = "run-1", "defect_fix_1_0"


def _captured(name: str) -> str:
    return (CAPTURED / name).read_text(encoding="utf-8")


def _workspace(root: Path, *files: str) -> Path:
    for relative in files:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text("\n", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _nothing_is_held_between_tests():
    yield
    tests_only_writes.release(RUN, STAGE)
    unit_failure_side.release(RUN, STAGE)


def _begin(monkeypatch: pytest.MonkeyPatch, root: Path, description: str, *, switch: str = "on") -> list[tuple]:
    from app.observability import defect_ledger

    monkeypatch.setenv("TESTS_ONLY_WRITES", "on")
    monkeypatch.setenv("UNIT_TEST_FIX_BY_FAILURE", switch)
    monkeypatch.setattr(defect_fix_modes, "_the_suite_is_green", lambda state, workspace: True)
    notes: list[tuple] = []
    monkeypatch.setattr(defect_ledger, "note", lambda event, stage, **kw: notes.append((event, stage, kw.get("detail"))))
    defect = Defect(description=description, severity="major", reproduction_steps="Run the project's unit test command.",
                    expected_behavior="Every unit test passes.", actual_behavior="The unit test command exits non-zero.",
                    owner="backend")
    state = {"repository": SimpleNamespace(root_path=str(root)), "test_round": 1, "current_sprint_index": 0}
    defect_fix_modes.begin(state, {"configurable": {"app_run_id": RUN}}, RemediationCycle(sprint_goal="g", defects=[defect]),
                           0, STAGE)
    return notes


def _briefing() -> str:
    return defect_fix_modes.briefing({"test_round": 1}, {"configurable": {"app_run_id": RUN}}, 0)


def test_an_exception_raised_in_a_product_module_lets_the_first_attempt_change_the_product(monkeypatch, tmp_path) -> None:
    """pytest: `verify_password` raised `ValueError: Invalid salt` inside `tasks_api/auth.py` before the assertion."""
    root = _workspace(tmp_path, "tasks-api/tasks_api/auth.py", "tasks-api/tests/test_auth.py")

    notes = _begin(monkeypatch, root, _captured("unit-failure-pytest-9-an-error-raised-in-a-product-module.txt"))

    assert not tests_only_writes.holds(RUN, STAGE)
    assert notes and notes[0][0] == "mode" and notes[0][2].startswith("product code allowed at once")
    briefing = _briefing()
    assert "The failure is raised in the product's code" in briefing and "`tasks-api/tasks_api/auth.py`" in briefing
    assert "test files only" not in briefing


def test_a_product_file_that_does_not_compile_is_the_product_s_to_fix(tmp_path) -> None:
    """dotnet: `Program.cs(69,32): error CS1061` in the product's project."""
    root = _workspace(tmp_path, "notes-api/src/App/Program.cs", "notes-api/tests/UnitTests/NotesTests.cs")

    found = unit_failure_side.the_product_s(_captured("unit-failure-dotnet-8-a-product-file-does-not-compile.txt"), root)

    assert found == ["notes-api/src/App/Program.cs"]


@pytest.mark.parametrize("name, files", [
    # `server_test.go:64: expected status 200, got 404`: the test's own check was reached and reported.
    ("unit-failure-go-test-a-test-reports-a-wrong-status.txt", ("notes-api/main.go", "notes-api/server_test.go")),
    # The trace runs through `tasks_api/auth.py`, but the test replaced its store with a `MagicMock`.
    ("unit-failure-pytest-9-a-stand-in-replaces-the-store.txt", ("tasks-api/tasks_api/auth.py", "tasks-api/tests/test_auth.py")),
    # javac: the file that does not compile is a test.
    ("unit-failure-maven-a-test-file-does-not-compile.txt",
     ("notes-api/src/main/java/app/notes_api/NoteService.java", "notes-api/src/test/java/app/notes_api/NoteServiceTest.java")),
])
def test_a_failure_the_test_may_cause_keeps_the_first_attempt_to_the_tests(monkeypatch, tmp_path, name, files) -> None:
    notes = _begin(monkeypatch, _workspace(tmp_path, *files), _captured(name))

    assert tests_only_writes.holds(RUN, STAGE)
    assert notes[0][2].startswith("tests only")
    assert "The failure is raised in the product's code" not in _briefing()


def test_with_the_switch_off_the_owner_s_rule_holds_every_first_attempt(monkeypatch, tmp_path) -> None:
    root = _workspace(tmp_path, "tasks-api/tasks_api/auth.py", "tasks-api/tests/test_auth.py")

    _begin(monkeypatch, root, _captured("unit-failure-pytest-9-an-error-raised-in-a-product-module.txt"), switch="off")

    assert tests_only_writes.holds(RUN, STAGE)


def test_a_frame_of_a_file_the_workspace_does_not_hold_is_not_the_product_s(tmp_path) -> None:
    """The same captured trace in a workspace without that module: the file is not the project's."""
    root = _workspace(tmp_path, "tasks-api/tests/test_auth.py")

    assert unit_failure_side.the_product_s(
        _captured("unit-failure-pytest-9-an-error-raised-in-a-product-module.txt"), root) == []


def test_the_effects_report_follows_the_defects_sent_to_the_product() -> None:
    records = [
        {"kind": "defect", "event": "mode", "defect_id": "a", "detail": unit_failure_side.MODE},
        {"kind": "defect", "event": "fixed", "defect_id": "a"},
        {"kind": "defect", "event": "mode", "defect_id": "b", "detail": "tests only: the locked acceptance suite is green"},
        {"kind": "defect", "event": "fixed", "defect_id": "b"},
    ]

    assert "not reached" in unit_failure_side.effects_lines([])[0]
    assert "(1 fixed, 0 reverted)" in unit_failure_side.effects_lines(records)[0]


def test_what_the_fixer_and_the_ledger_read_avoids_the_banned_words() -> None:
    text = unit_failure_side.section(["notes-api/src/App/Program.cs"])

    assert text and not BANNED.search(text), text
    assert not BANNED.search(unit_failure_side.MODE)
