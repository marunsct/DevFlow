"""A locked test that waits for a record it never made is one no product can pass, wherever the suite is checked.

Pre-emptive linting must catch unpassable acceptance tests before locking the suite,
avoiding expensive dispute cycles during implementation.
"""

from __future__ import annotations

from app.acceptance import junit, suite
from app.stacks import contract, pack_named

#: The page as the product shows it before any test has made a record, and with one made.
FRESH_PAGE = '- main:\n  - heading "Notes" [level=1]\n  - textbox "Title"\n'
WITH_A_RECORD = FRESH_PAGE + '  - list:\n    - listitem:\n      - checkbox "Done"\n'


def test_the_one_list_every_caller_reads_carries_a_test_waiting_for_a_record_it_never_made(tmp_path) -> None:
    contract.write(tmp_path, pack_named("browser-javascript"), "notes", "Notes")
    result = suite.AcceptanceResult(ran=True, shows=FRESH_PAGE, report=junit.Report(found=True, tests=[
        junit.TestResult(name="[AC-2] acts on a note", outcome="failed",
                         message="Timeout\nCall log:\n - waiting for getByRole('checkbox', { name: 'Done', exact: true })\n"
                                 f"{suite._PAGE_MARK}{FRESH_PAGE}"),
        junit.TestResult(name="[AC-1] adds a note", outcome="failed", message=f"Timeout\n{suite._PAGE_MARK}{WITH_A_RECORD}"),
    ]))

    found = suite.tests_that_cannot_pass(tmp_path, result)

    assert any("`[AC-2] acts on a note`" in item and "starts from an empty product" in item for item in found)
