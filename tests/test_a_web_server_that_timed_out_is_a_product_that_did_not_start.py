"""A suite whose web server never answered before the runner's timeout is the product's defect, not a suite proving nothing.

Measured on a small-model run: the service's own start script ran a module that defines the application and never
listens, Playwright printed `Timed out waiting 60000ms from config.webServer.` and ran no test; the zero tests were
read as a suite that collects nothing, and QA was sent five rounds in twenty minutes to fix a start script it does not own.
"""
from __future__ import annotations

import re

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
OUTPUT = "\n> notes-api@0.1.0 test:acceptance\n> playwright test\n\nError: Timed out waiting 60000ms from config.webServer.\n\n"


def test_the_timeout_is_recorded_as_a_product_that_did_not_start():
    problem = suite.the_product_did_not_start(OUTPUT)
    assert problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert "Timed out waiting 60000ms" in problem
    assert not BANNED.search(problem.split("Its output:")[0])


def test_that_run_is_not_called_a_suite_that_proved_nothing(tmp_path):
    problem = suite.the_product_did_not_start(OUTPUT)
    result = suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance",
                                    report=junit.Report(found=True), output=OUTPUT, problem=problem)
    assert suite.vacuous_green(tmp_path, result) == []
