"""A note the suite was locked with, saying a named test fails, is not shipped once that test passes.

The release listed five "fails because of an error in the test's own code" notes while its own final
measurement ran 15 passed, 0 failed: the record read as a broken product. A note naming a test still
failing, or about a test's strength rather than its outcome, is kept.
"""
import json
import types

from app.acceptance import suite
from app.graph import delivery

PASSING = "[AC-2][AC-7] GET /notes returns a JSON array of notes"
FAILING = "[AC-5] DELETE /notes/{id} deletes a note or returns 404"

REFUTED = f"`{PASSING}` fails because of an error in the test's own code, not because the product is unbuilt"
STILL_FAILING = f"`{FAILING}` fails because of an error in the test's own code"
ABOUT_STRENGTH = f"AC-2: `{PASSING}` only asserts the status, never the body"


def _project(tmp_path):
    result = tmp_path / suite.RESULT_FILE
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({"ran": True, "passed": 1, "failed": 1, "criteria": {
        "AC-2": {"id": "AC-2", "text": "List", "status": "passed",
                 "tests": [{"name": PASSING, "outcome": "passed"}]},
        "AC-5": {"id": "AC-5", "text": "Delete", "status": "failed",
                 "tests": [{"name": FAILING, "outcome": "failed"}]},
    }}))
    return tmp_path


def test_only_the_refuted_note_is_dropped(tmp_path):
    root = _project(tmp_path)

    kept = suite.open_problems_still_true(root, [REFUTED, STILL_FAILING, ABOUT_STRENGTH])

    assert kept == [STILL_FAILING, ABOUT_STRENGTH]


def test_the_review_page_lists_no_refuted_note(tmp_path):
    root = _project(tmp_path)
    state = {"repository": types.SimpleNamespace(root_path=str(root)),
             "acceptance_open_problems": [REFUTED, STILL_FAILING]}

    page = delivery.evidence(state, 1, "goal")

    assert STILL_FAILING in page
    assert REFUTED not in page
