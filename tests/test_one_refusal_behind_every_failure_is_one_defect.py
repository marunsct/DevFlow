"""One refusal behind nearly every failing acceptance test is raised as one defect, not one per criterion (LR.53).

Measured on one run: 16 tests of 14 criteria all failed with `assert 401 == 201` - the product refused the token its own
sign-in issued - and each criterion got a fixer of its own, shown one test, who sent the file back unchanged; the
round ran ten fixers in three hours.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _failing(messages):
    return [{"id": f"AC-{n}", "tests": [{"name": f"t{n}", "outcome": "failed", "message": m}]}
            for n, m in enumerate(messages, 1)]


def test_the_same_refusal_everywhere_is_one_cause():
    failing = _failing(["assert 401 == 201\n where", "assert 401 == 200", "assert 401 in (400, 422)", "assert 401 == 204"])
    assert nodes.one_refusal_for_all(failing) == ("401", 4)
    # A body read after the refused call fails with no status of its own: the same cause (measured beside 401s).
    with_symptoms = _failing(["assert 401 == 201", "assert 401 == 200", "assert 401 == 201", "E   KeyError: 'id'",
                              "E   KeyError: 'id'"])
    assert nodes.one_refusal_for_all(with_symptoms) == ("401", 5)


def test_mixed_failures_or_too_few_criteria_keep_their_own_defects():
    assert nodes.one_refusal_for_all(_failing(["assert 401 == 201", "assert 404 == 200", "assert 500 == 200",
                                               "AssertionError: title"])) is None
    assert nodes.one_refusal_for_all(_failing(["assert 401 == 201", "assert 401 == 200"])) is None
    # An answer the tests expected is not a wrong one.
    assert nodes.one_refusal_for_all(_failing(["assert 404 == 404"] * 4)) is None


def test_any_one_wrong_answer_everywhere_is_one_cause():
    # Measured after a rewind of the same run: 12 tests answered 422 where they expected 201 or 200, 8 a KeyError after.
    failing = _failing(["assert 422 == 201"] * 3 + ["assert 422 == 200"] * 2 + ["E   KeyError: 'id'"] * 3)
    assert nodes.one_refusal_for_all(failing) == ("422", 8)


def _measured_with(root: Path, messages: list[str]) -> dict:
    """A locked suite whose last measurement failed one test of each criterion with each message; the round's state."""
    suite.save_criteria(root, [Criterion(f"AC-{n}", f"criterion {n}", "brief") for n in range(1, len(messages) + 1)])
    suite.lock(root)
    (root / suite.RESULT_FILE).write_text(json.dumps({
        "ran": True, "command": "npm test",
        "criteria": {entry["id"]: {**entry, "text": "", "status": "failed"} for entry in _failing(messages)},
    }))
    return {"repository": SimpleNamespace(root_path=str(root))}


def test_the_round_raises_it_alone_and_its_words_ban_the_product_s_nouns(tmp_path):
    state = _measured_with(tmp_path, ["assert 401 == 201", "assert 401 == 200", "assert 401 == 201", "assert 401 == 204"])

    [defect] = nodes.failing_due_defects(state, [])

    assert "4 acceptance tests across 4 criteria are all answered 401" in defect.description
    assert defect.severity == "blocking"
    told = " ".join([defect.description, defect.reproduction_steps, defect.expected_behavior, defect.actual_behavior])
    assert not BANNED.search(told)


def test_a_browser_runner_s_failed_ok_check_is_read_too():
    # Measured on one run: every write answered `500 {"detail":"Database write failed"}`; the page tests failed after,
    # finding nothing saved.
    not_ok = "Error: expect(response).toBeOK() failed\n\n    Call log:\n    \u2192 POST /api/x\n    \u2190 500 Internal Server Error\n"
    page = "Error: expect(locator).toBeVisible() failed\n    Locator: getByRole('link')"
    assert nodes.one_refusal_for_all(_failing([not_ok] * 4 + [page] * 3)) == ("500", 7)


def test_a_server_error_on_every_write_groups_with_fewer_of_the_failures():
    not_ok = "Error: expect(response).toBeOK() failed\n    \u2190 500 Internal Server Error\n"
    page = "Error: expect(locator).toBeVisible() failed"
    assert nodes.one_refusal_for_all(_failing([not_ok] * 4 + [page] * 8)) == ("500", 12)
    # A client error needs half.
    refused = "Error: expect(response).toBeOK() failed\n    \u2190 404 Not Found\n"
    assert nodes.one_refusal_for_all(_failing([refused] * 4 + [page] * 8)) is None
