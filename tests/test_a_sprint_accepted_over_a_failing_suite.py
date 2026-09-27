"""A review may not report a passing suite over a measured failing one.

The milestone review decides whether a sprint is delivered, and it decides by
reading. The harness does not have to read: every command whose runner printed a
summary line is in the execution ledger with its own `tests`, `passed` and
`failed`.

Measured on run-df4dc6f5's third sprint. The ledger recorded `npm test` - the
project's own gating command - eight times in the four minutes before the review:

    10:23:50  npm test   tests=21  passed=15  failed=6
    10:24:57  npm test   tests=21  passed=15  failed=6
    10:25:32  npm test   tests=21  passed=15  failed=6
    10:26:56  npm test   tests=21  passed=15  failed=6

and the review returned:

    Executed npm run test successfully; all tests passed.
    No blocking or major violations found.
    Status: accepted

Three minor findings, none of them the six failures, and `sprint_3_summary.md`
went out saying "Status: Completed" over "Passed: 15, Failed: 6".

`app.analysis.verification_claims` exists for this exact fault one layer down -
"do not claim to have done what was not done" - and checks a specialist's claimed
commands against the ledger. Nothing checked the reviewer's.

A reviewer may legitimately accept a sprint with known failures deferred. What it
may not do is accept one while reporting the suite passed, so the remedy names
the numbers rather than arguing about judgement.

Nothing here names a language or a runner: the counts come from
`sandbox._RUNNER_TOTALS`, which reads TAP, jest, vitest, pytest, cargo and go, and
a sprint built in something it cannot parse reports no counts and is not gated.
"""

from __future__ import annotations

import json

import pytest

from app.graph.workflow import (
    _a_red_suite_the_review_called_green,
    _the_suite_the_ledger_measured,
)


class _Repository:
    def __init__(self, root: str) -> None:
        self.root_path = root


@pytest.fixture
def a_ledger(tmp_path, monkeypatch):
    """A workspace whose execution ledger this test writes."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace-run-df4dc6f5-0000-0000"
    root.mkdir()

    from app.tools.sandbox import _ledger_path

    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(*entries: dict) -> dict:
        path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
        return {"repository": _Repository(str(root)), "sprint_attempts": []}

    return _write


def _a_test_run(at: str, tests: int, passed: int, failed: int, command=("npm", "test")):
    return {
        "at": at,
        "command": list(command),
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "returncode": 0 if failed == 0 else 1,
    }


AN_INSTALL = {"at": "2026-09-26T10:20:00+00:00", "command": ["npm", "install"], "returncode": 0}

#: What run-df4dc6f5's sprint 3 recorded, four minutes before it was accepted.
THE_MEASUREMENT = _a_test_run("2026-09-26T10:26:56+00:00", 21, 15, 6)


class TestTheSprintThatWasAccepted:
    def test_a_measured_failure_blocks_acceptance(self, a_ledger):
        state = a_ledger(AN_INSTALL, THE_MEASUREMENT)

        assert _a_red_suite_the_review_called_green(state) != ""

    def test_the_message_names_the_numbers(self, a_ledger):
        """The remedy is the measurement, not an argument about judgement."""
        state = a_ledger(AN_INSTALL, THE_MEASUREMENT)

        message = _a_red_suite_the_review_called_green(state)

        assert "21 case(s)" in message
        assert "15 passed" in message
        assert "6 failed" in message

    def test_it_is_marked_as_something_that_must_be_fixed(self, a_ledger):
        """`MUST FIX` is the prefix the rest of this pipeline already routes on."""
        state = a_ledger(AN_INSTALL, THE_MEASUREMENT)

        assert _a_red_suite_the_review_called_green(state).startswith("MUST FIX")

    def test_it_offers_the_honest_alternative(self, a_ledger):
        """Deferring a failure is legitimate. Reporting it as a pass is not."""
        state = a_ledger(AN_INSTALL, THE_MEASUREMENT)

        assert "blocking finding" in _a_red_suite_the_review_called_green(state)


class TestNotBlockingWhatItShould:
    def test_a_passing_suite_is_silent(self, a_ledger):
        state = a_ledger(AN_INSTALL, _a_test_run("2026-09-26T10:30:00+00:00", 21, 21, 0))

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_later_green_run_settles_it(self, a_ledger):
        """The last measurement is the truth, which is what a fix looks like."""
        state = a_ledger(
            AN_INSTALL,
            THE_MEASUREMENT,
            _a_test_run("2026-09-26T10:31:00+00:00", 21, 21, 0),
        )

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_runner_that_reported_no_counts_is_not_gated(self, a_ledger):
        """A stack whose runner this harness cannot parse must still be able to
        finish a sprint. The same rule `_record_sprint_summary` follows."""
        state = a_ledger(AN_INSTALL)

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_an_empty_ledger_is_not_evidence(self, a_ledger):
        state = a_ledger()

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_an_unreadable_workspace_does_not_stop_a_run(self, tmp_path):
        """A gate that cannot read must not fail a sprint that passed everything."""
        state = {"repository": _Repository(str(tmp_path / "gone")), "sprint_attempts": []}

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_state_with_no_repository_does_not_raise(self):
        assert _a_red_suite_the_review_called_green({}) == ""


class TestTheWindowIsThisAttempt:
    def test_an_earlier_attempt_s_failure_does_not_block_this_one(self, a_ledger):
        """A sprint that failed, was re-planned and now passes must be able to pass.

        The window opens where the last recorded attempt closed, which is the
        same window `_record_sprint_summary` counts in - so this gate and the
        sprint summary cannot disagree about what the suite did.
        """
        state = a_ledger(
            _a_test_run("2026-09-26T09:00:00+00:00", 21, 15, 6),
            _a_test_run("2026-09-26T11:00:00+00:00", 21, 21, 0),
        )
        state["sprint_attempts"] = [
            {"sprint_index": 0, "number": 1, "ended_at": "2026-09-26T10:00:00+00:00"}
        ]

        assert _a_red_suite_the_review_called_green(state) == ""

    def test_a_failure_inside_this_attempt_still_blocks(self, a_ledger):
        state = a_ledger(
            _a_test_run("2026-09-26T09:00:00+00:00", 21, 21, 0),
            _a_test_run("2026-09-26T11:00:00+00:00", 21, 15, 6),
        )
        state["sprint_attempts"] = [
            {"sprint_index": 0, "number": 1, "ended_at": "2026-09-26T10:00:00+00:00"}
        ]

        assert _a_red_suite_the_review_called_green(state) != ""

    def test_the_gate_and_the_summary_read_the_same_number(self, a_ledger):
        """Two readings of one suite is how a report starts contradicting a gate.

        The counts, field by field, rather than the whole dict: the gate also
        carries the run's exit code, which the summary does not print, and
        pinning the shape would make adding that a failure rather than a change.
        """
        from app.agents.sprint_summary import count_test_cases
        from app.tools.sandbox import read_execution_ledger

        state = a_ledger(AN_INSTALL, THE_MEASUREMENT)

        measured = _the_suite_the_ledger_measured(state)
        printed = count_test_cases(
            read_execution_ledger(state["repository"].root_path, limit=1000)
        )

        assert printed == {"tests": 21, "passed": 15, "failed": 6}
        for field in ("tests", "passed", "failed"):
            assert measured[field] == printed[field], field


class TestItIsWiredIntoTheReview:
    def test_the_gate_runs_before_the_sprint_is_committed(self):
        """Checked on the source: the node is a closure over the compiled graph.

        What matters is the ordering. `commit_milestone` records the sprint as a
        state worth returning to, and a red suite must not reach it.
        """
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        gate = source.index("_a_red_suite_the_review_called_green(state)\n        if red:")
        commit = source.index("commit_milestone(", gate)

        assert gate < commit

    def test_it_is_bounded_by_the_revision_limit(self):
        """A suite that cannot be made to pass must end the run, not loop.

        Without the bound this would send every review back for ever, which is
        worse than the acceptance it replaces because the run never finishes.
        """
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        start = source.index("red = _a_red_suite_the_review_called_green(state)")
        block = source[start : start + 1800]

        assert "MAX_MILESTONE_REVISIONS" in block
        assert "_record_sprint_summary" in block, "an ending gets a summary like every other"
