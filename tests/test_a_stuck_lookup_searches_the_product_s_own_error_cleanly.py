"""A stuck fixer's lookup searches the product's own error, cleaned of what the removals left behind.

Measured over three days of runs: a third of the searches went out as the harness's or the test runner's wording
("Requests at the edges of the interface contract ...", "A fix was tried and reverted ...", Playwright's "Process from
config.webServer was not able to start"), and some as "path to : ' ' does not exist" - none of it anything others wrote.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import stuck_lookup
from app.tools.lookups import cleaned


def _error_of(actual: str, description: str = "") -> str:
    return stuck_lookup._the_error_line(SimpleNamespace(actual_behavior=actual, description=description))


def test_the_harness_s_own_wording_is_not_searched():
    said = ("Requests at the edges of the interface contract are not handled: `GET /notes/{id}` at id `x` answered "
            "500 (it said: Internal Server Error)")

    assert _error_of(said, said) == ""


def test_a_revert_notice_is_not_searched():
    said = "A fix was tried and reverted, because it broke what passed before it: the product no longer builds"

    assert _error_of(said) == ""


def test_the_runner_s_start_line_gives_way_to_the_product_s_error():
    said = ("Error: Process from config.webServer was not able to start. Exit code: 1\n"
            "Caused by: org.hibernate.HibernateException: Unable to determine Dialect without JDBC metadata")

    found = _error_of(said)

    assert "HibernateException" in found and "webServer" not in found


def test_a_runner_start_line_alone_is_not_searched():
    assert _error_of("Error: Timed out waiting 60000ms from config.webServer.") == ""


def test_an_emptied_quote_and_its_punctuation_are_dropped():
    assert cleaned("java.sql.SQLException: path to ' ': ' ' does not exist") == (
        "java.sql.SQLException: path to does not exist")


def test_a_short_quoted_value_stays():
    assert cleaned("KeyError: 'id'") == "KeyError: 'id'"
