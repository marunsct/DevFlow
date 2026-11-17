"""A test round's log states what the acceptance suite measured, not only the defects it raised.

Its owner read "did not report 5 failing acceptance criteria" as a round's
result: that round's product did not start, every criterion failed and the
start failure stood for the rest, so it looked better than the next round,
where the product started and 2 of 13 passed - while the run page said 2.
"""

from __future__ import annotations

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


def test_the_round_logs_it_and_names_its_defects_as_defects(tmp_path, caplog):
    """The owner reads the run log's line for each round as that round's result."""
    import logging

    from workflow_nodes import a_test_round, reported

    measured = {"ran": True, "passed": 5, "failed": 29,
                "criteria": {"AC-1": {"status": "passed"}, "AC-2": {"status": "failed"}, "AC-3": {"status": "passed"}}}

    with caplog.at_level(logging.INFO):
        a_test_round(tmp_path, [reported("[AC-2] The list is empty")],
                     patches={"app.graph.acceptance_nodes.suite.last_result": lambda root: measured})

    said = [record.getMessage() for record in caplog.records if record.getMessage().startswith("test_round_1")]
    assert "test_round_1: the acceptance suite measured 2 of 3 criteria passing (5 of 34 tests)" in said
    assert not any("did not report" in line for line in said)
