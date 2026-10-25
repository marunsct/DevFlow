"""A test that meets a 500 carries the error the service logged, so a fixer sees the cause and not only the status.

Measured on a small-model run: sign-up answered 500 and the tests said `assert 500 == 201`. The service had logged
`TypeError: 'password' is an invalid keyword argument for Account` (a route and a model that disagreed on a field's
name). Fixers never saw the log, rewrote files for an hour and reported they could not find the cause.
"""
from __future__ import annotations

from pathlib import Path

from app.acceptance import junit, suite
from app.stacks import pack_named

LOG = """INFO:     Started server process [42]
INFO:     127.0.0.1:50000 - "POST /signup HTTP/1.1" 500 Internal Server Error
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File "/x/.venv/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/x/tasks-api/tasks_api/auth.py", line 31, in signup
    account = Account(username=body.username, password=hashed)
  File "<string>", line 4, in __init__
TypeError: 'password' is an invalid keyword argument for Account
INFO:     127.0.0.1:50001 - "POST /signup HTTP/1.1" 500 Internal Server Error
"""


def _project(tmp_path: Path, log: str | None = LOG) -> None:
    (tmp_path / "tasks-api" / "test-results").mkdir(parents=True)
    if log is not None:
        (tmp_path / "tasks-api" / "test-results" / "service.log").write_text(log)


def _result(*tests: junit.TestResult) -> suite.AcceptanceResult:
    return suite.AcceptanceResult(ran=True, exit_code=1, command="pytest acceptance",
                                  report=junit.Report(found=True, tests=list(tests)))


def test_the_error_is_named_with_where_the_project_raised_it(tmp_path):
    _project(tmp_path)
    errors = suite.the_errors_a_service_logged(tmp_path, "tasks-api")
    assert errors == ["TypeError: 'password' is an invalid keyword argument for Account "
                      "(File \"/x/tasks-api/tasks_api/auth.py\", line 31, in signup)"]


def test_a_failing_test_with_a_server_error_carries_it_and_others_do_not(tmp_path):
    _project(tmp_path)
    result = _result(
        junit.TestResult(name="test_signup", outcome="failed", message="assert 500 == 201"),
        junit.TestResult(name="test_missing", outcome="failed", message="assert 404 == 200"),
        junit.TestResult(name="test_ok", outcome="passed", message=""),
    )

    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)

    signup, missing, ok = result.report.tests
    assert "The service logged this while the suite ran" in signup.message and "invalid keyword argument" in signup.message
    assert missing.message == "assert 404 == 200" and ok.message == ""


def test_no_log_or_no_traceback_leaves_the_failures_as_they_were(tmp_path):
    _project(tmp_path, log=None)
    result = _result(junit.TestResult(name="t", outcome="failed", message="assert 500 == 201"))
    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)
    assert result.report.tests[0].message == "assert 500 == 201"

    _project_two = tmp_path / "other"
    (_project_two / "p" / "test-results").mkdir(parents=True)
    (_project_two / "p" / "test-results" / "service.log").write_text("INFO: started\n")
    assert suite.the_errors_a_service_logged(_project_two, "p") == []


def test_the_message_is_not_extended_twice(tmp_path):
    _project(tmp_path)
    result = _result(junit.TestResult(name="t", outcome="failed", message="assert 500 == 201"))
    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)
    once = result.report.tests[0].message
    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)
    assert result.report.tests[0].message == once


def test_the_python_pack_writes_the_service_log_to_a_file_not_a_pipe():
    conftest = pack_named("python-http-api").files["acceptance/conftest.py"]
    assert 'LOG = PROJECT / "test-results" / "service.log"' in conftest
    assert "stdout=subprocess.PIPE" not in conftest and "stdout=self._log" in conftest
    compile(conftest.replace("{{package}}", "pkg"), "conftest", "exec")
