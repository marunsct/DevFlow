"""Failing tests that stop at one step with one answer are one blocking defect, not one per criterion (LF.1259).

Measured on one run: 80 locked tests failed - 37 answered 429 where they expected 201, 18 threw "Login rate limited" at
one line of the suite's shared helper, 8 threw "Login failed with status 401" at that helper, 13 were answered 404 on
every route under one prefix, 4 failed otherwise. The rule for one refusal read only asserted statuses, saw 37 of 80
answered 429 and never fired; each criterion got its own defect and fixer for hours, and the one cause of every 404 (a
prefix given twice) was raised as eight symptom defects beside it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes as nodes
from app.graph import workflow
from app.sprint import Defect, RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _direct(expected, received, line, call=""):
    """A Playwright status check that got another answer, failing at the test's own line."""
    frame = f"  {line - 1} |   {call}\n> {line} |   expect(res.status()).toBe({expected});\n" if call else ""
    return (f"Error: expect(received).toBe(expected) // Object.is equality\n\nExpected: {expected}\nReceived: {received}\n\n"
            f"{frame}\n    at /work/tests/acceptance/items.spec.js:{line}:26")


def _thrown_by_the_helper(text, line, caller):
    return (f"Error: {text}\n\n> {line} |     throw new Error(`...`);\n\n"
            f"    at login (/work/tests/acceptance/test-utils.js:{line}:11)\n"
            f"    at /work/tests/acceptance/items.spec.js:{caller}:19")


def _page(line):
    return f"Error: expect(locator).toBeVisible() failed\n\n    at /work/tests/acceptance/page.spec.js:{line}:30"


#: Calls on the routes under one prefix the service never serves.
_UNDER_ONE_PREFIX = ["request.get(`/api/items/${id}`);", "request.post('/api/items', { data });",
                     "request.patch(`/api/items/${id}`, { data });", "request.delete(`/api/items/${id}`);",
                     "request.get('/api/items?owner=me');"]


def _failing(groups):
    """Criteria `AC-1`... each failing the tests given: a list of messages per criterion."""
    return [{"id": f"AC-{n}", "text": f"criterion {n}", "status": "failed",
             "tests": [{"name": f"AC-{n} test {k}", "file": "tests/acceptance/items.spec.js", "outcome": "failed",
                        "message": m} for k, m in enumerate(messages, 1)]}
            for n, messages in enumerate(groups, 1)]


def _round(root: Path, groups) -> dict:
    """A locked suite whose last measurement failed these tests; the round's state."""
    failing = _failing(groups)
    suite.save_criteria(root, [Criterion(e["id"], e["text"], "brief") for e in failing])
    suite.lock(root)
    (root / suite.RESULT_FILE).write_text(json.dumps({
        "ran": True, "command": "npx playwright test", "criteria": {e["id"]: e for e in failing}}))
    return {"repository": SimpleNamespace(root_path=str(root))}


def _the_measured_mix():
    line = iter(range(100, 1000, 7))
    groups = []
    # Ten criteria refused by the limit: 37 asserted 429s and 18 thrown by the helper's line 75.
    for n in range(10):
        groups.append([_direct(201, 429, next(line)) for _ in range(4 if n < 7 else 3)]
                      + [_thrown_by_the_helper("Login rate limited", 75, next(line)) for _ in range(2 if n < 8 else 1)])
    # Four criteria whose sign-in the helper's line 79 reports refused 401.
    groups += [[_thrown_by_the_helper("Login failed with status 401", 79, next(line)) for _ in range(2)]
               for _ in range(4)]
    # Four criteria answered 404 on every route under one prefix.
    for count in (4, 3, 3, 3):
        groups.append([_direct(200, 404, ln := next(line), _UNDER_ONE_PREFIX[ln % 5]) for _ in range(count)])
    # Two criteria failing otherwise.
    groups += [[_page(next(line)), _page(next(line))] for _ in range(2)]
    return groups


def _told(defect) -> str:
    return " ".join([defect.description, defect.reproduction_steps, defect.expected_behavior, defect.actual_behavior])


def test_errors_the_shared_helper_throws_naming_the_limit_count_with_the_limit():
    tests = [t for e in _failing(_the_measured_mix()) for t in e["tests"]]
    assert len(tests) == 80
    assert nodes.one_refusal_for_all(_failing(_the_measured_mix())) == ("429", 55)


def test_the_measured_mix_raises_the_limit_and_each_other_shared_step_once(tmp_path):
    state = _round(tmp_path, _the_measured_mix())

    defects = nodes.failing_due_defects(state, [])

    limit, *steps = defects
    [refused] = [d for d in steps if "401" in d.description]
    [unserved] = [d for d in steps if "404" in d.description]
    assert len(steps) == 2
    assert [d.severity for d in defects] == ["blocking"] * 3
    assert "55 acceptance tests" in limit.description and "429" in limit.description
    assert "8 acceptance tests across 4 criteria" in refused.description
    assert "test-utils.js:79" in refused.description and "401" in refused.description
    assert "13 acceptance tests across 4 criteria" in unserved.description
    assert "/api/items" in unserved.description and "404" in unserved.description
    # The hint for a prefix nobody serves: compare what the service serves with the paths the tests call.
    assert "serves" in unserved.actual_behavior and "paths the tests call" in unserved.actual_behavior
    # Each carries its own tests as evidence; the limit's are not the others'.
    assert len(refused.evidence) == 8 and len(unserved.evidence) == 13
    assert {r["criterion"] for r in unserved.evidence} == {"AC-15", "AC-16", "AC-17", "AC-18"}
    assert not {r["test"] for r in limit.evidence} & {r["test"] for r in [*refused.evidence, *unserved.evidence]}
    for defect in defects:
        assert not BANNED.search(_told(defect))


def test_a_shared_step_is_raised_first_and_its_criteria_not_again(tmp_path):
    other = [_direct(201, 422, 500 + n, call) for n, call in
             enumerate(["request.post('/api/users', { data });", "request.post('/api/projects', { data });",
                        "request.post('/api/auth/login', { data });"])]
    groups = [[_direct(200, 404, 40 + 5 * k + n, _UNDER_ONE_PREFIX[n % 5]) for n in range(k + 2)] for k in range(3)]
    state = _round(tmp_path, [*groups, *[[m] for m in other]])

    defects = nodes.failing_due_defects(state, [])

    first, *rest = defects
    assert first.severity == "blocking" and "9 acceptance tests across 3 criteria" in first.description
    assert "/api/items" in first.description
    assert [d.description.split("]")[0] for d in rest] == ["[AC-4", "[AC-5", "[AC-6"]


def test_small_or_different_failures_keep_each_criterion_s_own_defect(tmp_path):
    # One 404 on each of three prefixes, a helper throwing two statuses, a page check: different steps, answers.
    groups = [
        [_direct(200, 404, 10, "request.get('/api/users');")],
        [_direct(200, 404, 20, "request.get('/api/projects');")],
        [_direct(200, 404, 30, "request.get('/api/items');")],
        [_thrown_by_the_helper("Login failed with status 401", 79, 40)],
        [_thrown_by_the_helper("Login failed with status 403", 79, 50)],
        [_thrown_by_the_helper("Login failed with status 500", 79, 60)],
        [_page(70)],
    ]
    state = _round(tmp_path, groups)

    defects = nodes.failing_due_defects(state, [])

    assert [d.description.split("]")[0] for d in defects] == [f"[AC-{n}" for n in range(1, 8)]


def test_two_tests_at_one_step_are_not_yet_one_cause(tmp_path):
    state = _round(tmp_path, [[_direct(200, 404, 10, _UNDER_ONE_PREFIX[0])], [_direct(200, 404, 20, _UNDER_ONE_PREFIX[1])],
                              [_page(30)], [_page(40)]])

    assert len(nodes.failing_due_defects(state, [])) == 4


def test_the_request_is_read_from_the_test_s_own_file_when_its_message_shows_none(tmp_path):
    spec = tmp_path / "tests" / "acceptance" / "items.spec.js"
    spec.parent.mkdir(parents=True)
    body = ["test('x', async ({ request }) => {", "  const res = await request.get(`/api/items/${id}`);",
            "  expect(res.status()).toBe(200);", "});"]
    spec.write_text("\n".join(body * 4) + "\n")
    lines = [3, 7, 11, 15]
    # The fourth answered otherwise, so not every failure is the one refusal.
    state = _round(tmp_path, [[_direct(200, 404, ln)] for ln in lines[:3]]
                   + [[_direct(201, 422, 99, "request.post('/api/users', { data });")]])

    first, *_ = nodes.failing_due_defects(state, [])

    assert "3 acceptance tests across 3 criteria" in first.description and "/api/items" in first.description


def test_the_one_step_spares_the_criteria_this_round_raises_again():
    def defect(description):
        return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                      actual_behavior="a", owner="backend")

    cycle = RemediationCycle(sprint_goal="g", defects=[defect("[AC-3] Create - the acceptance suite says no."),
                                                       defect("[AC-4] List - the acceptance suite says no.")])
    one = SimpleNamespace(description="9 acceptance tests across 3 criteria stop at one step, `/api/items`, answered 404.")
    again = SimpleNamespace(description="[AC-4] List - the acceptance suite says no.")

    after = workflow.superseded_by_one_cause(cycle, [one, again])

    assert [d.status for d in after.defects] == ["superseded", "open"]
