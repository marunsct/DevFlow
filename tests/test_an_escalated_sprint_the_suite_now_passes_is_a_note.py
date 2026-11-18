"""A sprint an escalation accepted unfinished, whose tests the locked suite passes in full at release, is a note (LR.21).

Measured on one run: a sprint accepted after three re-plans, a later sprint made all 31 locked tests pass, 10 of 10
hidden and 7 of 7 quality tests passed - and the run was called not deliverable for the old sprint.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import completion_verdict as cv
from app.acceptance import junit, suite
from app.graph import delivery

SPRINT = "Sprint 'Sign-up and sign-in' was re-planned 3 times and still could not be accepted: AC-2 failed.\\n\\nreport"
NOTE = "every locked test passes at release"


def test_an_escalated_sprint_is_a_note_with_or_without_the_release_s_words():
    assert not cv.is_blocking(f"An escalation left this open (DR-14): {NOTE}: {SPRINT}")
    # Calibrated on hidden and quality tests (deep review 2026-11-18, B4): 105 runs carried an escalated sprint and
    # 18 lost a test, no more often than any run did.
    assert not cv.is_blocking(f"An escalation left this open (DR-14): {SPRINT}")


def _released(tmp_path, monkeypatch, *, locked: bool, issue: str) -> list[str]:
    """The release's gaps for a run carrying `issue`, whose suite (when `locked`) passes in full at release."""
    from app.analysis import integration_checks

    if locked:
        (tmp_path / suite.STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / suite.STATE_FILE).write_text(json.dumps({"lock": {"files": {}}}))
        (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True}))
    green = suite.AcceptanceResult(ran=True, exit_code=0, command="npx playwright test",
                                   report=junit.Report(found=True, tests=[junit.TestResult(name="[AC-2] signs in",
                                                                                         outcome="passed")]))
    monkeypatch.setattr(suite, "run", lambda root, **kwargs: green)  # the suite's run in the sandbox
    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    update = delivery.release(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "known_issues": [issue]},
        {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(tmp_path), allow_subdirectories=True),
    )
    return [str(gap) for gap in update.get("completion_gaps") or []]


@pytest.mark.parametrize(("locked", "issue", "noted"), [
    (True, SPRINT, True),
    (False, SPRINT, False),
    (True, "Design review left open: [blocking] the export endpoint has no auth", False),
])
def test_the_release_says_so_only_for_an_unfinished_sprint_and_a_green_suite(tmp_path, monkeypatch, locked, issue,
                                                                             noted):
    gaps = _released(tmp_path, monkeypatch, locked=locked, issue=issue)

    escalated = [gap for gap in gaps if gap.startswith("An escalation left this open")]
    assert len(escalated) == 1
    assert (NOTE in escalated[0]) is noted
