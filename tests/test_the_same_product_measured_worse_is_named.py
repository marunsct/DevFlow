"""Every suite measurement is kept, and the same product measuring worse than it did is named.

Measured on one run: 17 of 17 passed, ten minutes later 3 of 17 with not a line of the product changed, and only the
latest result was kept, so nothing showed the fall.
"""
from __future__ import annotations

from app.acceptance import junit, suite


def _ran(passed: int, failed: int) -> suite.AcceptanceResult:
    tests = [junit.TestResult(name=f"p{n}", outcome="passed") for n in range(passed)]
    tests += [junit.TestResult(name=f"f{n}", outcome="failed") for n in range(failed)]
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=tests, found=True))


def test_the_same_product_measuring_worse_is_kept_and_named(tmp_path):
    suite._keep_in_the_history(tmp_path, _ran(17, 0), "product-a")
    suite._keep_in_the_history(tmp_path, _ran(3, 14), "product-a")
    [worse] = suite.same_product_measured_worse(tmp_path)
    assert worse["passed"] == 3 and worse["tests"] == 17
    assert len((tmp_path / suite.HISTORY_FILE).read_text().splitlines()) == 2


def test_another_product_or_a_better_result_is_not_named(tmp_path):
    suite._keep_in_the_history(tmp_path, _ran(17, 0), "product-a")
    suite._keep_in_the_history(tmp_path, _ran(3, 14), "product-b")
    suite._keep_in_the_history(tmp_path, _ran(18, 0), "product-b")
    assert suite.same_product_measured_worse(tmp_path) == []
