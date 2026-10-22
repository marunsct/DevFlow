"""A page-check defect the page check no longer finds is closed, not handed to fixer after fixer.

Measured on one run: sprint 4's page check raised a contrast finding, the
contrast defects beside it were fixed, and the page-check defect still went to a
fixer in each of two rounds. The second spent fifteen minutes, every reply at
its reasoning budget, re-reading a stylesheet that already passed - a page-check
defect names no criterion and no test, so nothing that closes a defect by
measurement reached it.

The page check reads the harness's last run of the suite, which every fix's
measurement saves. A finding of the same kind still there - another count of
the same broken rule - keeps the defect open.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import ci
from app.agents.specialists import ReportedDefect
from app.sprint import Defect, RemediationCycle

CONTRAST = "An accessibility check of the page finds 1 serious or critical rule(s) broken: color-contrast."


def _state(root: Path) -> dict[str, Any]:
    return {"repository": SimpleNamespace(root_path=str(root)), "test_round": 2}


def _defect(description: str = CONTRAST, source: str = "page check") -> Defect:
    return Defect(
        description=description, severity="major", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="ui_ux", source=source,
    )


def _found(description: str) -> ReportedDefect:
    return ReportedDefect(
        description=description, severity="major", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="ui_ux",
    )


@pytest.fixture
def page(monkeypatch):
    """What the page check finds now, settable by each test."""
    shown: dict[str, list] = {"now": []}
    monkeypatch.setattr("app.graph.acceptance_nodes.interface_defects", lambda state: list(shown["now"]))
    monkeypatch.setattr("app.graph.acceptance_nodes.suite.last_result", lambda root: {"ran": True})
    return shown


def _measured(root: Path, label: str = "after defect_fix_2_0") -> None:
    ci.save(root, ci.Snapshot(label=label))


class TestBeforeAFixerIsSent:
    def test_it_is_closed_when_the_page_check_finds_nothing_of_its_kind(self, tmp_path, page):
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path)

        update = _closed_if_an_earlier_fix_resolved_it(
            _state(tmp_path), RemediationCycle(sprint_goal="s", defects=[_defect()]), 0
        )

        assert update is not None
        closed = update["remediation"].defects[0]
        assert closed.status == "fixed"
        assert "no longer finds it" in closed.resolution

    def test_the_same_kind_of_finding_still_there_keeps_it_open(self, tmp_path, page):
        from app.graph.workflow import _closed_if_an_earlier_fix_resolved_it

        _measured(tmp_path)
        page["now"] = [_found(CONTRAST.replace("finds 1", "finds 2"))]

        assert _closed_if_an_earlier_fix_resolved_it(
            _state(tmp_path), RemediationCycle(sprint_goal="s", defects=[_defect()]), 0
        ) is None

    def test_another_kind_of_finding_does_not_keep_it_open(self, tmp_path, page):
        from app.graph.workflow import _a_page_check_that_passes_now

        _measured(tmp_path)
        page["now"] = [_found("The interface is not styled: the only stylesheet is the one the scaffold wrote.")]

        assert _a_page_check_that_passes_now(_state(tmp_path), _defect())

    def test_no_measurement_since_the_report_proves_nothing(self, tmp_path, page):
        from app.graph.workflow import _a_page_check_that_passes_now

        _measured(tmp_path, "after the work orders")

        assert _a_page_check_that_passes_now(_state(tmp_path), _defect()) == ""

    def test_a_defect_another_check_raised_is_never_read_as_one(self, tmp_path, page):
        from app.graph.workflow import _a_page_check_that_passes_now

        _measured(tmp_path)

        assert _a_page_check_that_passes_now(_state(tmp_path), _defect(source="test round")) == ""


class TestAtTheRound:
    def test_the_round_s_own_run_closes_it(self, tmp_path, page):
        from app.graph.workflow import _closed_by_this_round_s_measurement

        _measured(tmp_path, "after the work orders")
        cycle = RemediationCycle(sprint_goal="s", defects=[_defect()])

        assert _closed_by_this_round_s_measurement(_state(tmp_path), cycle, 2).defects[0].status == "fixed"

    def test_not_while_the_page_still_shows_it(self, tmp_path, page):
        from app.graph.workflow import _closed_by_this_round_s_measurement

        page["now"] = [_found(CONTRAST)]
        cycle = RemediationCycle(sprint_goal="s", defects=[_defect()])

        assert _closed_by_this_round_s_measurement(_state(tmp_path), cycle, 2).defects[0].status == "open"
