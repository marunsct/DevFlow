"""The QA lead reads a sprint's unbuilt criteria failing as expected, not as faulty tests (LF.1532).

Measured on a medium run (thorough delivery), sprint 2: its tests were written before sprint 2 was built, as the suite
is written a sprint at a time. The run the QA lead was shown had every test of the sprint's new criteria failing with
405 - the endpoints were not built yet - and it sent the suite back as faulty four times, then the run waited for a
person. Each failure of a criterion the sprint builds is now named "expected now"; a failure of a criterion an earlier
sprint built stays as it was, since that is evidence.

The run summary below is the one the QA lead was given in that run, copied verbatim from its transcript.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.acceptance import by_sprint, suite
from app.acceptance.criteria import Criterion
from app.acceptance.suite import AcceptanceResult, CriterionResult
from app.stacks import contract, pack_named

CAPTURED = Path(__file__).parent / "captured" / "acceptance-summary-a-sprint-s-new-endpoints-answer-405-before-its-build.txt"
#: The criteria that sprint built once its tests were locked, as its review said ("This sprint adds the tests of ...").
THIS_SPRINT = ["AC-2", "AC-4", "AC-5"]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _captured() -> AcceptanceResult:
    """The captured run as the result it was rendered from: each criterion's row and its failed tests."""
    criteria: dict[str, CriterionResult] = {}
    current: CriterionResult | None = None
    for line in CAPTURED.read_text().splitlines():
        if row := re.match(r"- (AC-\d+) (\w+): (.*)", line):
            current = criteria[row[1]] = CriterionResult(row[1], row[3], row[2].lower())
        elif failed := re.match(r"    failed: (.*?) - (Error: .*)", line):
            current.tests.append({"name": failed[1], "outcome": "failed", "message": failed[2]})
    return AcceptanceResult(ran=True, exit_code=1, command="the suite", criteria=criteria)


def _workspace(root: Path, result: AcceptanceResult) -> Path:
    contract.write(root, pack_named("python-http-api"), "product", "Product")
    suite.save_criteria(root, [Criterion(c.id, c.text, "brief") for c in result.criteria.values()])
    assert by_sprint.decide(root, fast=False)
    return root


def _lines_after(text: str, test_name: str) -> list[str]:
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith(f"    failed: {test_name} - "))
    return lines[at + 1:at + 2]


def test_each_failure_of_a_criterion_the_sprint_builds_is_named_expected_now(tmp_path):
    result = _captured()
    root = _workspace(tmp_path, result)
    by_sprint.open_for(root, THIS_SPRINT, sprint=2, of=4)

    shown = by_sprint.what_running_it_showed(root, result)

    assert _lines_after(shown, "[AC-2] creating a task returns 201 with id") == [
        "      expected now: AC-2 is built by this sprint"]
    assert _lines_after(shown, "[AC-4] submitting an invalid priority returns 422 with INVALID_PRIORITY error_code") == [
        "      expected now: AC-4 is built by this sprint"]
    assert shown.count("expected now: AC-2 is built by this sprint") == 9
    assert shown.count("expected now: AC-4 is built by this sprint") == 2
    assert shown.count("expected now: AC-5 is built by this sprint") == 7
    assert "no evidence against the test" in shown.splitlines()[0]


def test_a_failure_of_a_criterion_an_earlier_sprint_built_stays_evidence(tmp_path):
    result = _captured()
    root = _workspace(tmp_path, result)
    by_sprint.open_for(root, THIS_SPRINT, sprint=2, of=4)

    shown = by_sprint.what_running_it_showed(root, result)

    assert _lines_after(shown, "[AC-8] after logout the access token is rejected with 401") == [
        "- AC-9 NOT_YET_DUE: Task CRUD operations work correctly"]
    assert "AC-8 is built" not in shown


def test_at_the_release_no_failure_is_called_expected(tmp_path):
    """The release's criteria were built by the sprints before it: a failure there is evidence."""
    result = _captured()
    root = _workspace(tmp_path, result)
    by_sprint.open_for(root, THIS_SPRINT, sprint=4, of=4, at_release=True)

    shown = by_sprint.what_running_it_showed(root, result)

    assert "expected now" not in shown
    assert shown == result.summary()


def test_what_the_qa_lead_is_told_about_them_uses_none_of_the_banned_words(tmp_path):
    result = AcceptanceResult(ran=True, command="the suite", criteria={
        "AC-1": CriterionResult("AC-1", "An item can be added", "passed"),
        "AC-2": CriterionResult("AC-2", "An item can be renamed", "failed", [
            {"name": "test_ac2_holds", "outcome": "failed", "message": "AssertionError: the product answered 404"}]),
    })
    root = _workspace(tmp_path, result)
    by_sprint.open_for(root, ["AC-2"], sprint=2, of=2)

    shown = by_sprint.what_running_it_showed(root, result)

    assert "expected now: AC-2 is built by this sprint" in shown
    assert not BANNED.search(shown)
