"""A suite locked again while the product does not start says no test ran, not "0 test(s) ... every criterion is covered".

Measured on one run: a repaired suite was locked again after drafting, against a product that did not start yet; the
decision read "0 test(s) over 18 criteria; every criterion is covered and the QA lead approved", which reads as a
suite that holds no tests.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes


def _result(tests, problem=""):
    return SimpleNamespace(report=SimpleNamespace(tests=[object()] * tests), problem=problem)


def test_a_product_that_did_not_start_is_named_as_why_no_test_ran():
    said = acceptance_nodes.what_the_lock_ran(_result(0, f"{suite.PRODUCT_DID_NOT_START}: no test could reach it."), 18)
    assert said.startswith("no test ran against the product at this lock: it does not start yet")
    assert "18 criteria" in said and "0 test(s)" not in said


def test_a_suite_that_ran_says_its_count_as_before():
    assert acceptance_nodes.what_the_lock_ran(_result(11), 18) == "11 test(s) over 18 criteria"
