"""A product that is listening but never answers the readiness request with a success is told so (found on the sweep).

Measured on one run (a PHP service): every route answered 500, the suite's readiness request timed out after 60 s of
connections accepted and closed, and the defect said only that the product did not start - for two fix rounds and a
re-plan. The development server's log names no status, and its "started" line was not read as listening.
"""
from __future__ import annotations

from app.acceptance import suite

PHP_OUTPUT = (
    "Error: Timed out waiting 60000ms from config.webServer.\n"
    "[WebServer] [Mon Nov 16 20:47:58 2026] PHP 8.4.27 Development Server (http://127.0.0.1:41234) started\n"
    + "".join(f"[WebServer] [Mon Nov 16 20:48:{n:02d} 2026] 127.0.0.1:4{n:04d} Accepted\n"
              f"[WebServer] [Mon Nov 16 20:48:{n:02d} 2026] 127.0.0.1:4{n:04d} Closing\n" for n in range(10, 30))
)


def test_listening_with_no_status_in_the_log_says_it_started_and_its_requests_fail():
    said = suite.the_product_did_not_start(PHP_OUTPUT)
    assert said.startswith(suite.PRODUCT_DID_NOT_START)
    assert "The product started" in said
    assert "not answered with a success" in said


def test_a_status_in_the_log_is_still_named():
    output = "Error: Timed out waiting 60000ms from config.webServer.\nUvicorn running on http://127.0.0.1:8000\nINFO: 127.0.0.1 - \"GET /health HTTP/1.1\" 404 Not Found\n"
    assert "answered 404" in suite.the_product_did_not_start(output)


def test_a_product_that_never_listened_is_as_before():
    said = suite.the_product_did_not_start("Error: Timed out waiting 60000ms from config.webServer.\nFatal error: x\n")
    assert "The product started" not in said


def test_the_words_a_fixer_is_given_name_no_product_and_no_banned_word():
    import re

    said = suite.the_product_did_not_start(PHP_OUTPUT)
    lead = said[:said.index("Its output:")]
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", lead, re.I)
