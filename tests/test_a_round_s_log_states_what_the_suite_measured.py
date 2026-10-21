"""A test round's log states what the acceptance suite measured, not only the defects it raised.

Its owner read "did not report 5 failing acceptance criteria" as a round's
result: that round's product did not start, every criterion failed and the
start failure stood for the rest, so it looked better than the next round,
where the product started and 2 of 13 passed - while the run page said 2.
"""

from __future__ import annotations

import inspect

from app.graph import workflow


def test_the_measurement_is_counted_from_the_suite_s_last_result(tmp_path, monkeypatch):
    result = {"ran": True, "passed": 5, "failed": 29,
              "criteria": {"AC-1": {"status": "passed"}, "AC-2": {"status": "failed"}, "AC-3": {"status": "passed"}}}
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: result)

    assert workflow.the_round_s_measurement(tmp_path) == (
        "the acceptance suite measured 2 of 3 criteria passing (5 of 34 tests)"
    )


def test_a_suite_that_did_not_run_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: {})
    assert workflow.the_round_s_measurement(tmp_path) == "the acceptance suite did not run"


def test_the_round_logs_it_and_names_its_defects_as_defects():
    source = inspect.getsource(workflow)
    assert 'logger.info("test_round_%d: %s", test_round, the_round_s_measurement(' in source
    assert "did not report %d failing acceptance criteria" not in source
