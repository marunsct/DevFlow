"""A locked test sent for repair on a harness check's finding is settled, not sent back, once no check names it.

Measured on one run: a check misread a right locked test and reopened the suite for its repair. The check was
corrected while the repair was open and no longer named the test, which needed no change - but the review kept
answering "this repair was sent for it and has not changed it", and the writers were sent back four times, over 45
minutes, to change a test with nothing wrong in it. A test a dispute ruled wrong is a judgement no check can run
again, and is still sent back while it is left as it was.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import junit, suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named
from workflow_nodes import an_acceptance_review_measured

PY = '''import httpx


def test_ac7_a_note_keeps_its_title(base_url):
    note = httpx.post(base_url + "/notes", json={"title": "Milk"}).json()
    assert isinstance(note["title"], str)
    assert note["title"] == "Milk"


def test_ac8_notes_are_listed(base_url):
    assert httpx.get(base_url + "/notes").status_code == 200
'''

FINDING = ("`test_ac7_a_note_keeps_its_title` filters for a value it never made: no test step creates a note whose "
           "title it then looks for.")


def _a_locked_suite(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes", "Notes")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "test_api.py").write_text(PY)
    suite.save_criteria(tmp_path, [Criterion("AC-7", "A note keeps its title", "brief"),
                                   Criterion("AC-8", "Notes are listed", "brief")])
    suite.lock(tmp_path)


def _reopened(tmp_path, monkeypatch, *, by_a_dispute=False):
    """The locked suite reopened for `FINDING`, as a test round (or a dispute) reopens it; the repair's own rewrite
    in place is off, so the writers are the ones sent."""
    monkeypatch.setenv("NAMED_TEST_REWRITE", "false")
    _a_locked_suite(tmp_path)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    reopened = acceptance_nodes.reopen_the_suite_for(state, [FINDING], reclassifying=by_a_dispute)
    suite.unlock(tmp_path)
    return reopened


def _measured(root):
    """The product as measured when the repair came back: the test still fails, on the product."""
    return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
        junit.TestResult(name="acceptance/test_api.py::test_ac7_a_note_keeps_its_title", outcome="failed",
                         message="assert 'Milk ' == 'Milk'"),
        junit.TestResult(name="acceptance/test_api.py::test_ac8_notes_are_listed", outcome="passed")]))


def test_a_test_sent_on_a_check_s_finding_that_no_longer_holds_is_settled_and_the_suite_locks_again(
        tmp_path, monkeypatch):
    _reopened(tmp_path, monkeypatch)

    update = an_acceptance_review_measured(tmp_path, _measured, state={
        "acceptance_round": 1, "acceptance_return_to": "test_and_triage"})

    assert not [problem for problem in update.get("acceptance_feedback") or [] if "has not changed" in problem]
    assert update["stage"] != "acceptance_author"
    assert suite.is_locked(tmp_path)
    assert any("test_ac7_a_note_keeps_its_title" in str(record) and "no longer holds" in str(record)
               for record in update.get("decisions") or [])


def test_a_test_whose_finding_is_still_raised_and_left_as_it_was_is_still_sent_back(tmp_path, monkeypatch):
    _reopened(tmp_path, monkeypatch)

    [left] = suite.tests_left_unrepaired(tmp_path, _measured(tmp_path), still_found=[FINDING])

    assert "`test_ac7_a_note_keeps_its_title`" in left
    assert suite.tests_whose_finding_no_longer_holds(tmp_path, _measured(tmp_path), still_found=[FINDING]) == []


def test_a_test_a_dispute_ruled_wrong_and_left_as_it_was_is_still_sent_back(tmp_path, monkeypatch):
    _reopened(tmp_path, monkeypatch, by_a_dispute=True)

    [left] = suite.tests_left_unrepaired(tmp_path, _measured(tmp_path), still_found=[])

    assert "`test_ac7_a_note_keeps_its_title`" in left


def test_a_finding_is_not_taken_as_gone_on_a_product_that_did_not_start(tmp_path, monkeypatch):
    _reopened(tmp_path, monkeypatch)
    not_started = suite.AcceptanceResult(ran=True, exit_code=1, problem=suite.PRODUCT_DID_NOT_START, report=junit.Report(
        found=True, tests=[junit.TestResult(name="acceptance/test_api.py::test_ac7_a_note_keeps_its_title",
                                            outcome="failed", message="Connection refused")]))

    [left] = suite.tests_left_unrepaired(tmp_path, not_started, still_found=[])

    assert "`test_ac7_a_note_keeps_its_title`" in left
