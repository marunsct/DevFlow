"""A QA lead's reason that sets a test aside for what the product does, not what its criterion says, names nothing.

Measured on two runs: "the implementation includes createdAt and updatedAt, which are not part of the criterion"
set aside the tests of a criterion listing a record's three fields, and QA loosened them; "the implementation parses
the body as JSON regardless of header and responds with 200 instead of the 415 the specification defines" set aside
the specification's own test. The prompt already said the code is not the standard; nothing checked the answer.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents import suite_dispute

NAMES = ["[AC-1] POST /notes creates a note and DELETE removes it", "[AC-18] PUT with non-JSON content type returns 415",
         "[AC-2] GET /notes returns list of created notes"]


def test_a_reason_about_what_the_implementation_returns_keeps_the_test_locked():
    answer = SimpleNamespace(cannot_pass=[
        "[AC-1] POST /notes creates a note and DELETE removes it: the test asserts that the returned JSON contains only "
        "id, title and body; the implementation includes createdAt and updatedAt which are not part of the criterion and "
        "cause deep equality to fail.",
        "[AC-18] PUT with non-JSON content type returns 415: the test sends Content-Type: text/plain, but the implementation "
        "parses the body as JSON regardless of header and therefore responds with status 200 instead of the expected 415 "
        "defined by the specification.",
    ])
    assert suite_dispute.tests_it_names(answer, NAMES) == []


def test_a_reason_that_the_test_asks_for_what_the_criterion_does_not_still_names_it():
    answer = SimpleNamespace(cannot_pass=[
        "[AC-2] GET /notes returns list of created notes: the test expects the list sorted by title, which the criterion "
        "does not require; the response returns them in creation order.",
        "[AC-1] POST /notes creates a note and DELETE removes it: it asserts two notes exist although its own steps "
        "created one.",
    ])
    named = suite_dispute.tests_it_names(answer, NAMES)
    assert len(named) == 2 and named[0].startswith("`[AC-1]") and named[1].startswith("`[AC-2]")


def test_the_judgement_itself():
    assert suite_dispute.judged_by_the_code("the actual response has an extra field and the test fails")
    assert not suite_dispute.judged_by_the_code("the test requires a header the brief never mentions")
    assert not suite_dispute.judged_by_the_code("")


def test_a_reason_whose_subject_is_the_product_s_own_symbol_is_still_the_product_s():
    """Measured on one run, twice: after a rewind the QA lead re-worded the same product-behaviour reason with the
    product's symbol as subject, and the earlier wording needed "the implementation"/"the product" to be named."""
    for why in ("StorageService.load() is never called, so data is not loaded on startup.",
                "the product never loads the existing notes.json on startup, so no data is persisted across restarts "
                "as the test expects.",
                "the restart handler never runs, and notes written before the restart are missing."):
        assert suite_dispute.judged_by_the_code(why), why
    assert not suite_dispute.judged_by_the_code("the test expects notes sorted by id, which the criterion never requires.")
    assert not suite_dispute.judged_by_the_code("it asserts a note it never created is present.")
