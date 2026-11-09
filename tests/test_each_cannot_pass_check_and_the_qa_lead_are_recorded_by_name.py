"""Each check inside `tests_that_cannot_pass` and the QA lead's findings are recorded under their own names (HR2.Q.1).

Measured: 36 checks were recorded as one bucket and the QA lead - the sender of 240 of the 295 items left open at the
lock - not at all, so no check's settle rate could be told apart.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite
from app.graph import acceptance_nodes


def test_the_result_remembers_which_check_raised_each_finding(monkeypatch, tmp_path):
    for name in ("tests_that_broke_themselves", "locators_that_do_not_exist"):
        pass
    monkeypatch.setattr(suite, "locators_that_do_not_exist", lambda root: ["`test_a` finds a locator nothing has"])
    monkeypatch.setattr(suite, "tests_that_broke_themselves", lambda root, result: ["`test_b` broke itself"])
    found = suite.tests_that_cannot_pass(tmp_path, None)
    assert found.checks.get("`test_a` finds a locator nothing has") == "locators_that_do_not_exist"
    assert found.checks.get("`test_b` broke itself") == "tests_that_broke_themselves"


def test_the_review_records_by_check_and_records_the_qa_lead():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert 'named.get(str(f), "tests_that_cannot_pass")' in source
    assert 'check_findings.noted(root, rounds, "qa_lead", findings)' in source
