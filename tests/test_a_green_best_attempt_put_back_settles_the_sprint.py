"""A sprint whose best attempt, put back as it runs out, passes every acceptance test settles, not planned again.

Measured on one run: a kept fix broke one acceptance test, the sprint ran out at 28 of 29, the settle rule read that
measurement, and only then was the best attempt (29 of 29, only unit tests failing) put back - and the green sprint
was planned again.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite
from app.graph import settle_when_green, workflow
from app.sprint import Defect


def _defect(description, source="acceptance suite", criteria=()):
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior="a", owner="backend", source=source, failing_criteria=list(criteria))


def _put_back_green(monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    monkeypatch.setattr(suite, "last_result", lambda root: {
        "ran": True, "passed": 29, "failed": 0,
        "criteria": {"AC-8": {"status": "passed"}, "AC-2": {"status": "passed"}}})
    monkeypatch.setattr(suite, "_command", lambda root: (["npx", "playwright", "test"], "bookmarks"))


def test_a_defect_about_criteria_that_pass_after_the_put_back_is_not_open(tmp_path, monkeypatch):
    _put_back_green(monkeypatch)
    broken = _defect("[AC-8] POST rejects a bad link - the acceptance suite says this does not work yet.", criteria=["AC-8"])
    unit = _defect("The unit tests fail. It says: 1 failing", source="test round")
    still = settle_when_green.open_after_the_put_back(tmp_path, [broken, unit])
    assert [d.status for d in still] == ["fixed", "open"]
    assert settle_when_green.applies(tmp_path, still, 1) is True
    # Without the put-back reading, the acceptance defect keeps the sprint from settling.
    assert settle_when_green.applies(tmp_path, [broken, unit], 1) is False


def test_the_round_asks_again_after_putting_the_best_back():
    source = inspect.getsource(workflow)
    at = source.index("put_back = best_attempt.restore_if_worse(")
    assert "settle_when_green.open_after_the_put_back(" in source[at:at + 800]
