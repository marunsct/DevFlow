"""While the locked acceptance suite is green, the first fix of a failing unit test writes test files only (plan item 12, behind `TESTS_ONLY_WRITES`).

Measured on two runs: fixes for "the unit tests fail" rewrote the product's files
too, broke the locked acceptance suite or other unit tests and were reverted
whole, and four wrong unit tests then shipped failing beside a green suite. With
the switch on, the first attempt at such a defect is refused every write to
application code - by the file tools and by the rewrite path's own file filter -
and a second attempt writes whatever it needs. Each attempt's mode is in the
defect ledger. Off, nothing changes.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.graph import defect_fix_modes
from app.sprint import Defect, RemediationCycle
from app.tools import tests_only_writes
from app.tools.repository import (
    RepositoryToolError, delete_approved_artifact, edit_approved_artifact, move_approved_artifact,
    write_approved_artifact,
)

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RUN, STAGE = "run-1", "defect_fix_3_0"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shop" / "tests").mkdir(parents=True)
    (tmp_path / "shop" / "cart.py").write_text("TOTAL = 0\n", encoding="utf-8")
    (tmp_path / "shop" / "tests" / "test_cart.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _nothing_is_held_between_tests():
    yield
    tests_only_writes.release(RUN, STAGE)
    tests_only_writes.release(None, STAGE)


def _in_stage(monkeypatch: pytest.MonkeyPatch, stage: str, run_id: str | None = RUN) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: stage)
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: run_id)


def test_a_held_fix_stage_may_not_change_product_code(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _in_stage(monkeypatch, STAGE)
    tests_only_writes.hold(RUN, STAGE)

    with pytest.raises(RepositoryToolError, match="writes tests only") as refused:
        edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    assert "`blockers`" in str(refused.value) and "Nothing was written." in str(refused.value)
    with pytest.raises(RepositoryToolError, match="writes tests only"):
        write_approved_artifact(project, "shop/cart.py", "TOTAL = 1\n")
    with pytest.raises(RepositoryToolError, match="Nothing was deleted."):
        delete_approved_artifact(project, "shop/cart.py")
    with pytest.raises(RepositoryToolError, match="Nothing was moved."):
        move_approved_artifact(project, "shop/cart.py", "shop/cart_old.py")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 0\n"
    assert not BANNED.search(str(refused.value))


@pytest.mark.parametrize("path", ["shop/tests/test_cart.py", "shop/tests/fixtures.json", "shop/pyproject.toml", "shop/NOTES.md"])
def test_its_tests_fixtures_configuration_and_notes_stay_writable(project: Path, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    _in_stage(monkeypatch, STAGE)
    tests_only_writes.hold(RUN, STAGE)

    body = {"toml": "[x]\n", "json": "{}\n"}.get(path.rsplit(".", 1)[-1], "def test_y():\n    assert True\n")
    write_approved_artifact(project, path, body)

    assert (project / path).is_file()


def test_a_stage_not_held_changes_product_code_as_before(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _in_stage(monkeypatch, STAGE)
    edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 1\n"


def test_only_the_held_stage_of_the_held_run_is_held(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tests_only_writes.hold(RUN, STAGE)
    _in_stage(monkeypatch, "defect_fix_3_1")
    edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    _in_stage(monkeypatch, STAGE, run_id="another-run")
    edit_approved_artifact(project, "shop/cart.py", "TOTAL = 1", "TOTAL = 2")
    _in_stage(monkeypatch, STAGE)
    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(project, "shop/cart.py", "TOTAL = 2", "TOTAL = 3")


def test_the_rewrite_path_is_offered_only_the_files_a_held_stage_may_write(project: Path) -> None:
    tests_only_writes.hold(RUN, STAGE)

    assert tests_only_writes.may_write(RUN, STAGE, project, "shop/tests/test_cart.py") is True
    assert tests_only_writes.may_write(RUN, STAGE, project, "shop/cart.py") is False
    assert tests_only_writes.may_write(RUN, STAGE, project, str(project / "shop" / "cart.py")) is False
    assert tests_only_writes.may_write(RUN, "defect_fix_3_1", project, "shop/cart.py") is True


def test_the_briefing_tells_the_fixer_what_it_may_write_and_what_to_do_if_the_product_is_wrong() -> None:
    assert tests_only_writes.briefing(RUN, STAGE) == ""
    tests_only_writes.hold(RUN, STAGE)
    text = tests_only_writes.briefing(RUN, STAGE)

    assert "test files only" in text and "`blockers`" in text and "next attempt may change the product" in text
    assert not BANNED.search(text), text
    assert not BANNED.search(tests_only_writes.explain_mode(True, unit_failure_beside_a_green_suite=True))
    assert not BANNED.search(tests_only_writes.explain_mode(False, unit_failure_beside_a_green_suite=True))


# --- which attempt runs in which mode ----------------------------------------


def _cycle(description: str, tries: int = 0, source: str = "", owner: str = "backend") -> RemediationCycle:
    defect = Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                    actual_behavior="a", owner=owner, source=source, fix_attempts=tries)
    return RemediationCycle(sprint_goal="g", defects=[defect])


def _begin(monkeypatch, tmp_path, cycle, *, green=True, switch="on"):
    from app.observability import defect_ledger

    monkeypatch.setenv("TESTS_ONLY_WRITES", switch)
    monkeypatch.setattr(defect_fix_modes, "_the_suite_is_green", lambda state, root: green)
    notes: list[tuple] = []
    monkeypatch.setattr(defect_ledger, "note", lambda event, stage, **kw: notes.append((event, stage, kw.get("detail"))))
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 3, "current_sprint_index": 0}
    defect_fix_modes.begin(state, {"configurable": {"app_run_id": RUN}}, cycle, 0, STAGE)
    return notes


def test_the_first_attempt_at_a_failing_unit_test_beside_a_green_suite_is_held_and_recorded(monkeypatch, tmp_path) -> None:
    notes = _begin(monkeypatch, tmp_path, _cycle("The unit tests fail. 2 failed."))

    assert tests_only_writes.holds(RUN, STAGE)
    assert notes and notes[0][0] == "mode" and notes[0][2].startswith("tests only")


def test_the_second_attempt_may_write_the_product_and_the_ledger_says_so(monkeypatch, tmp_path) -> None:
    notes = _begin(monkeypatch, tmp_path, _cycle("The unit tests fail. 2 failed.", tries=1))

    assert not tests_only_writes.holds(RUN, STAGE)
    assert notes[0][0] == "mode" and notes[0][2].startswith("product code allowed")


@pytest.mark.parametrize("what", ["suite not green", "not a unit test", "a mutation finding", "switch off"])
def test_every_other_fix_is_unrestricted_and_unrecorded(monkeypatch, tmp_path, what) -> None:
    cycle = _cycle("The unit tests fail. 2 failed.")
    kwargs = {}
    if what == "suite not green":
        kwargs["green"] = False
    elif what == "not a unit test":
        cycle = _cycle("[AC-2] Sign in fails")
    elif what == "a mutation finding":
        cycle = _cycle("The unit tests fail. 2 failed.", source="mutation")
    else:
        kwargs["switch"] = "off"

    notes = _begin(monkeypatch, tmp_path, cycle, **kwargs)

    assert not tests_only_writes.holds(RUN, STAGE) and notes == []


def test_the_mode_ends_with_the_stage() -> None:
    tests_only_writes.hold(RUN, STAGE)
    defect_fix_modes.end({"configurable": {"app_run_id": RUN}}, STAGE)
    assert not tests_only_writes.holds(RUN, STAGE)


def test_the_suite_is_green_only_when_it_ran_passed_and_no_due_criterion_fails(monkeypatch, tmp_path) -> None:
    from app.graph import acceptance_nodes, settle_when_green

    monkeypatch.setattr(settle_when_green, "the_locked_suite_is_green", lambda root: True)
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([], "cmd"))
    assert defect_fix_modes._the_suite_is_green({}, tmp_path) is True
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "AC-1"}], "cmd"))
    assert defect_fix_modes._the_suite_is_green({}, tmp_path) is False
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([], "cmd"))
    monkeypatch.setattr(settle_when_green, "the_locked_suite_is_green", lambda root: False)
    assert defect_fix_modes._the_suite_is_green({}, tmp_path) is False


def test_the_fix_stage_is_wired_to_the_modes() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert "defect_fix_modes.begin(state, config, cycle, defect_index, stage_name)" in source
    assert "defect_fix_modes.end(config, stage_name)" in source
    assert "defect_fix_modes.briefing(state, config, defect_index)" in source
    assert "defect_fix_modes.may_write(state, config, defect, root, path)" in source


def test_the_switch_is_an_experiment_that_ships_off() -> None:
    from app import switches

    assert "TESTS_ONLY_WRITES" in switches.EXPERIMENTS and "TESTS_ONLY_WRITES" not in switches.EXPERIMENTS_ON
    assert tests_only_writes.ON_BY_DEFAULT is False
    with mock.patch.dict("os.environ", {"TESTS_ONLY_WRITES": ""}):
        assert tests_only_writes.enabled() is False
