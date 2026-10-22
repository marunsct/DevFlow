"""A defect reported while a test command is failing needs no new test.

Measured on one run. Its first sprint ended every test round with the suite
red, and every fix was told it "MUST also add or update a regression test that
fails before your fix and passes after it". Nine such files were written in
three hours. Five could not run at all, one asserted that the failure
*happens* - "import fails before fix", `expect(errorOccurred).toBe(true)` -
and each became the next round's defect, to be fixed with one more.

A failing suite is already the test that fails before the fix and passes after
it. A new one is asked for when nothing catches the defect.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.specialists import build_defect_fix_request
from app.graph.workflow import _needs_a_new_test, _the_test_command_this_stage_left_failing
from app.sprint import Defect
from app.tools.sandbox import _ledger_path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "the-app-run-abc"
    root.mkdir()
    return root


def _ran(root: Path, *entries: dict) -> None:
    path = _ledger_path(str(root))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _entry(stage: str, code, command=("npm", "test"), category="test") -> dict:
    return {"stage": stage, "command": list(command), "category": category, "returncode": code, "error": None}


def _reported(files=("app/src/app.js",), required=True):
    return SimpleNamespace(regression_test_required=required, affected_files=list(files))


def test_the_command_a_round_left_failing_is_named(workspace) -> None:
    _ran(workspace, _entry("test_round_1", 0), _entry("test_round_1", 1))

    assert _the_test_command_this_stage_left_failing(str(workspace), "test_round_1") == (
        "npm test", "exited 1",
    )


def test_a_round_that_ended_green_left_nothing_failing(workspace) -> None:
    _ran(workspace, _entry("test_round_1", 1), _entry("test_round_1", 0))

    assert _the_test_command_this_stage_left_failing(str(workspace), "test_round_1") == ("", "")


def test_another_stage_s_failure_is_not_this_round_s(workspace) -> None:
    _ran(workspace, _entry("defect_fix_1_0", 1))

    assert _the_test_command_this_stage_left_failing(str(workspace), "test_round_1") == ("", "")


def test_no_new_test_is_asked_for_while_a_test_command_fails() -> None:
    assert not _needs_a_new_test(_reported(), "npm test")


def test_a_defect_nothing_catches_still_brings_its_test() -> None:
    assert _needs_a_new_test(_reported(), "")


def test_a_defect_in_the_tests_never_needed_one() -> None:
    assert not _needs_a_new_test(_reported(files=["app/tests/a.test.js"]), "")


def _brief(*, required: bool, caught_by: str = "") -> str:
    request = build_defect_fix_request(
        "The page does not load", "open it", "it loads", "it throws",
        ["app/src/app.js"], required, "/", caught_by=caught_by,
    )
    return request["messages"][0]["content"]


def test_the_fix_is_told_the_failing_command_is_its_proof() -> None:
    brief = _brief(required=False, caught_by="npm test")

    assert "`npm test` already fails because of this" in brief
    assert "Add no new test for this defect" in brief
    assert "MUST also add" not in brief


def test_the_new_test_is_asked_for_as_a_test_of_the_right_behaviour() -> None:
    brief = _brief(required=True)

    assert "asserts the correct behaviour this defect broke" in brief
    # The old wording, which one run read as a request for a test that expects
    # the failure.
    assert "fails before your fix" not in brief


def test_a_defect_remembers_what_caught_it() -> None:
    defect = Defect(
        description="d", severity="major", reproduction_steps="r", expected_behavior="e",
        actual_behavior="a", owner="backend", regression_test_required=False,
        caught_by="npm test",
    )

    assert defect.caught_by == "npm test"
    assert Defect.model_validate(defect.model_dump()).caught_by == "npm test"
