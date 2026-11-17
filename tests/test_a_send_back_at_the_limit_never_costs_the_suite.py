"""A send-back at the review's limit never costs the run a suite it could have locked, and is once per lock.

Found in a code review: the at-the-limit send-backs (held only in part, no product could pass, too weak) returned a
suite that might not run or might prove nothing; with no rounds left the run failed, although the suite that ran
before the send-back was lockable. The three "once" flags were also never cleared, so a reopened suite never got them.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.acceptance import junit, suite
from tests.test_an_output_given_in_place_of_another_is_held_whole import BRIEF, WEAK
from workflow_nodes import an_acceptance_review_measured

FAILING = suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
    junit.TestResult(name="acceptance.test_cli.test_ac3_json", outcome="failed", message="no product"),
    junit.TestResult(name="acceptance.test_cli.test_ac9_json_with_top", outcome="failed", message="no product")]))
CANNOT_RUN = suite.AcceptanceResult(ran=False, exit_code=2, problem="the suite does not load", output="SyntaxError")
STATE = {"document": SimpleNamespace(text=BRIEF)}


def _sent_back_at_the_limit(tmp_path):
    """A suite whose outputs are held only in part, sent back once at the review's limit to be strengthened."""
    files = {"run.json": json.dumps({"command": ["run"], "report": "r.xml"}), "test_cli.py": WEAK}
    update = an_acceptance_review_measured(tmp_path, FAILING, files=files, state={**STATE, "acceptance_round": 3})
    assert update["stage"] == "acceptance_author"
    return tmp_path / "notes" / "acceptance"


def test_a_send_back_that_leaves_a_suite_that_cannot_run_puts_the_suite_before_it_back(tmp_path):
    folder = _sent_back_at_the_limit(tmp_path)
    (folder / "test_cli.py").write_text("broken(")
    (folder / "test_extra.py").write_text("added by the send-back")

    update = an_acceptance_review_measured(tmp_path, CANNOT_RUN, state={**STATE, "acceptance_round": 5})

    assert update["stage"] == "acceptance_review"
    assert (folder / "test_cli.py").read_text() == WEAK and not (folder / "test_extra.py").exists()


def test_the_once_at_the_limit_send_back_is_available_again_after_the_lock(tmp_path):
    _sent_back_at_the_limit(tmp_path)
    approves = SimpleNamespace(approved=True, findings=[])
    an_acceptance_review_measured(tmp_path, FAILING, reviews=(approves,), state={**STATE, "acceptance_round": 3})
    assert suite.is_locked(tmp_path)

    again = an_acceptance_review_measured(tmp_path, FAILING, state={**STATE, "acceptance_round": 3})

    assert again["stage"] == "acceptance_author"
    assert again["acceptance_feedback"][0].startswith("Strengthen only the tests named below")
