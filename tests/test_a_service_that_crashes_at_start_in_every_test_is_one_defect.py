"""A service that crashes at start in every test's setup is one "does not start" defect, not one per criterion.

A suite that starts the service per test runs every test, and each fails at
setup with the same crash. Measured on a gate run: one startup crash became
six criterion defects, six fixers rewrote their criteria's files, all six were
left open - the check for a product that never started asked only when no
test ran at all.
"""
from __future__ import annotations

from app.acceptance import junit, suite

CRASH = (
    'failed on setup with "Failed: The service did not start:\n'
    "INFO:     Waiting for application startup.\n"
    "ERROR:    Traceback (most recent call last):\n"
    '  File "/w/items-api/items_api/main.py", line 22, in lifespan\n'
    "    conn = database.get_db_sync(DATA_DIR)\n"
    "AttributeError: module 'items_api.database' has no attribute 'get_db_sync'\n"
    'ERROR:    Application startup failed. Exiting."'
)


def _report(*tests):
    return junit.Report(found=True, tests=list(tests))


def test_every_failure_at_the_service_s_start_is_the_one_start_problem():
    report = _report(
        junit.TestResult(name="test_ac1_signs_up", outcome="failed", message=CRASH),
        junit.TestResult(name="test_ac16_health", outcome="failed", message=CRASH),
        junit.TestResult(name="test_ac17_start_script_exists", outcome="passed"),
    )
    problem = suite.every_failure_is_the_start(report)
    assert problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert "get_db_sync" in problem


def test_one_failure_for_another_reason_means_the_product_started():
    report = _report(
        junit.TestResult(name="test_ac1_signs_up", outcome="failed", message=CRASH),
        junit.TestResult(name="test_ac2_signs_in", outcome="failed", message="assert 401 == 200"),
    )
    assert suite.every_failure_is_the_start(report) == ""
    assert suite.every_failure_is_the_start(_report(junit.TestResult(name="t", outcome="passed"))) == ""


def test_the_run_records_it_when_tests_ran(tmp_path):
    from xml.sax.saxutils import escape, quoteattr

    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("python-http-api"), "items", "Items")
    (tmp_path / "items" / "acceptance").mkdir(parents=True)
    (tmp_path / "items" / "acceptance" / "test_api.py").write_text(
        "def test_ac1_signs_up(client):\n    pass\n\n\ndef test_ac16_health(client):\n    pass\n")
    cases = "".join(
        f'<testcase classname="acceptance.test_api" name="{name}">'
        f"<error message={quoteattr(CRASH)}>{escape(CRASH)}</error></testcase>"
        for name in ("test_ac1_signs_up", "test_ac16_health"))

    def the_suite_s_runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / "test-results" / "acceptance.xml").write_text(
            f'<testsuites><testsuite name="acceptance" tests="2">{cases}</testsuite></testsuites>')
        return {"returncode": "1"}

    result = suite.run(tmp_path, runner=the_suite_s_runner, save=False)

    assert result.ran and result.problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert "get_db_sync" in result.problem
