"""A test command that exited non-zero has not produced a green suite.

`_a_red_suite_the_review_called_green` refuses a sprint whose measured suite is
failing, and decided by reading `failed` from the execution ledger. That is not
the whole question.

A composite test command runs more than one runner. `npm test` chaining
`node --test` and `npx playwright test` is the shape this harness sees most, and
`sandbox._RUNNER_TOTALS` parses the summary line it recognises - the first
runner's. If a later runner fails, its cases are never added up, so the ledger
records a green count beside a non-zero exit code.

Measured on one run, which COMPLETED. Six of its ledger entries carry counts
and a failing exit code, five of them reading

    npm test   tests=27  passed=27  failed=0  returncode=1

Reading `failed` alone was silent on all five: the false green this gate exists
to prevent, reached by another route.

`a_suite_that_did_not_pass` now decides, and both callers select the same ledger
entry through `last_test_run`, because two separate searches for "the last test
run" is how a gate and a report start disagreeing about which run they mean.

Nothing here names a runner. Any two commands chained by any manifest produce the
same shape, and an entry with no exit code recorded is not evidence of failure -
older entries predate the field.
"""

from __future__ import annotations

import json

import pytest

from app.agents.sprint_summary import a_suite_that_did_not_pass, last_test_run
from app.graph.workflow import (
    _a_red_suite_the_review_called_green,
    _the_suite_the_ledger_measured,
)


class _Repository:
    def __init__(self, root: str) -> None:
        self.root_path = root


@pytest.fixture
def a_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace-run-a000000b-0000-0000"
    root.mkdir()

    from app.tools.sandbox import _ledger_path

    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(*entries: dict) -> dict:
        path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
        return {"repository": _Repository(str(root)), "sprint_attempts": []}

    return _write


#: One run's own entry, verbatim in every field that matters.
THE_FALSE_GREEN = {
    "at": "2026-09-27T02:44:35.427416+00:00",
    "role": "testing_specialist",
    "command": ["npm", "test"],
    "working_directory": "task-manager",
    "returncode": 1,
    "passed": 27,
    "failed": 0,
    "tests": 27,
}


class TestTheEntryThatWentThrough:
    def test_it_is_now_refused(self, a_ledger):
        state = a_ledger(THE_FALSE_GREEN)

        assert _a_red_suite_the_review_called_green(state) != ""

    def test_the_message_says_the_command_failed(self, a_ledger):
        state = a_ledger(THE_FALSE_GREEN)

        message = _a_red_suite_the_review_called_green(state)

        assert "command this sprint's suite is measured by failed" in message
        assert "exited 1" in message

    def test_it_explains_why_the_counts_look_green(self, a_ledger):
        """Otherwise the lead is asked to reconcile two numbers with no account."""
        state = a_ledger(THE_FALSE_GREEN)

        message = _a_red_suite_the_review_called_green(state)

        assert "chains runners" in message
        assert "first" in message

    def test_it_is_marked_as_something_that_must_be_fixed(self, a_ledger):
        state = a_ledger(THE_FALSE_GREEN)

        assert _a_red_suite_the_review_called_green(state).startswith("MUST FIX")

    def test_the_exit_code_reaches_the_gate(self, a_ledger):
        state = a_ledger(THE_FALSE_GREEN)

        assert _the_suite_the_ledger_measured(state)["returncode"] == 1


class TestWhatMustStaySilent:
    def test_a_passing_command_with_passing_counts(self, a_ledger):
        state = a_ledger({**THE_FALSE_GREEN, "returncode": 0})

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_an_entry_with_no_exit_code_recorded(self, a_ledger):
        """Older entries predate the field; a run nobody measured is not a failure."""
        entry = {k: v for k, v in THE_FALSE_GREEN.items() if k != "returncode"}

        assert _a_red_suite_the_review_called_green(a_ledger(entry)) == ""

    def test_a_null_exit_code(self, a_ledger):
        state = a_ledger({**THE_FALSE_GREEN, "returncode": None})

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_later_passing_run_settles_it(self, a_ledger):
        """The last measurement is the truth, which is what a fix looks like."""
        state = a_ledger(
            THE_FALSE_GREEN,
            {**THE_FALSE_GREEN, "at": "2026-09-27T02:47:36+00:00", "returncode": 0},
        )

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_non_test_command_that_failed_is_not_gated(self, a_ledger):
        """`npm install` exiting 1 is not a suite result."""
        state = a_ledger({
            "at": "2026-09-27T02:00:00+00:00",
            "command": ["npm", "install"],
            "returncode": 1,
        })

        assert _a_red_suite_the_review_called_green(state) == ""


class TestTheCountsAndTheExitCodeAreOneReading:
    def test_both_callers_select_the_same_entry(self, a_ledger):
        """Two searches for "the last test run" is how they start disagreeing."""
        from app.agents.sprint_summary import count_test_cases
        from app.tools.sandbox import read_execution_ledger

        state = a_ledger(
            {**THE_FALSE_GREEN, "at": "2026-09-27T02:00:00+00:00", "returncode": 0},
            THE_FALSE_GREEN,
        )
        entries = read_execution_ledger(state["repository"].root_path, limit=1000)

        chosen = last_test_run(entries)
        counts = count_test_cases(entries)

        assert chosen["at"] == THE_FALSE_GREEN["at"]
        assert counts["tests"] == chosen["tests"]

    def test_the_predicate_reads_both_fields(self):
        assert a_suite_that_did_not_pass({"failed": 6, "returncode": 0})
        assert a_suite_that_did_not_pass({"failed": 0, "returncode": 1})
        assert not a_suite_that_did_not_pass({"failed": 0, "returncode": 0})
        assert not a_suite_that_did_not_pass({"failed": 0})
        assert not a_suite_that_did_not_pass(None)

    def test_the_summary_still_prints_only_the_counts(self, a_ledger):
        """The exit code is the gate's business; the summary's numbers are unchanged."""
        from app.agents.sprint_summary import count_test_cases
        from app.tools.sandbox import read_execution_ledger

        state = a_ledger(THE_FALSE_GREEN)

        assert count_test_cases(
            read_execution_ledger(state["repository"].root_path, limit=1000)
        ) == {"tests": 27, "passed": 27, "failed": 0}
