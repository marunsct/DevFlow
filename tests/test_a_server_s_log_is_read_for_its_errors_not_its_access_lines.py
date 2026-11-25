"""A server's log is read for the errors it states and their frames in the product's own files, never for its access
lines; a log of access lines alone states no cause (FX.1, LF.1410).

Measured on two medium runs: access lines (`"POST /api/register HTTP/1.1" 500 Internal Server Error`) were kept as the
server's errors and filled the twelve lines a defect carries, so a traceback ending `no such table: users` was dropped
from seven fixers' briefs; on the other run the saved log was five such lines, which silenced the note that the
handler hid the cause for three fixers (77 minutes, no change kept). Every handler there answered
`status.HTTP_500_INTERNAL_SERVER_ERROR`, a named constant the search for the lines answering 5xx did not know. Other
stacks' error lines (PHP, Java, .NET, Rust, structured logs) were not read as errors at all.

The two fixtures are real: a suite's output from one run, and a product's route file from the other.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes

FIXTURES = Path(__file__).parent / "fixtures" / "server_logs"
#: The saved log of the run whose handlers answered 500 without a log line.
ACCESS_LINES_ONLY = "\n".join(
    f'INFO:     127.0.0.1:{port} - "POST /api/register HTTP/1.1" 500 Internal Server Error'
    for port in (59196, 59204, 59206, 59214, 59224))
#: What the failing test of that run printed.
RECEIVED_500 = ("auth.spec.js:23:1 › [AC-1] registration creates a new user\n\n    Error: expect(received).toBe(expected) "
                "// Object.is equality\n\n    Expected: 201\n    Received: 500\n")


def test_the_traceback_behind_the_access_lines_is_what_the_server_logged():
    output = (FIXTURES / "a_traceback_behind_access_lines.txt").read_text(encoding="utf-8")

    logged = suite.what_the_server_logged(output)

    assert "no such table: users" in logged
    # Its frames in the product's own files, not the libraries'.
    assert "routers/users.py" in logged and "site-packages" not in logged
    assert 'HTTP/1.1"' not in logged


@pytest.mark.parametrize("line", [
    r"PHP Fatal error:  Uncaught Slim\Exception\HttpNotFoundException: Not found. in /app/src/RoutingMiddleware.php:76",
    "org.sqlite.SQLiteException: [SQLITE_ERROR] SQL error or missing database (no such table: notes)",
    "Caused by: org.hibernate.dialect.DialectResolver$NoDialectException: Cannot determine a dialect",
    "java.lang.NullPointerException: the repository is null",
    "System.InvalidOperationException: Sequence contains no elements",
    "fail: Microsoft.AspNetCore.Server.Kestrel[13]",
    "error[E0599]: no method named `fetch` found for struct `Db`",
    "thread 'main' panicked at src/main.rs:10:5:",
    'time=2026-11-25T10:00:00Z level=error msg="database is closed"',
])
def test_each_stack_s_error_line_is_kept(line):
    assert line.split()[0] in suite.what_the_server_logged(f"[WebServer] {line}\n")


def test_one_error_logged_again_with_other_numbers_is_kept_once_and_the_last_errors_are_kept():
    lines = [f"[WebServer] 2026-11-25 05:05:{n:02d} WARN SQLException: database is locked, SQLState: {n}"
             for n in range(6)]
    lines += [f"[WebServer] KeyError: 'field_{n}'" for n in range(20)]
    lines += ["[WebServer] Caused by: java.io.FileNotFoundException: /data/notes.db (No such file or directory)"]

    logged = suite.what_the_server_logged("\n".join(lines))

    assert logged.count("database is locked") == 1
    assert "FileNotFoundException" in logged, "the root cause, logged last, is never the one cut"


def test_a_log_of_access_lines_alone_says_the_handler_hid_the_cause_and_where(tmp_path):
    routes = tmp_path / "service" / "app" / "routes"
    routes.mkdir(parents=True)
    shutil.copy(FIXTURES / "a_handler_that_answers_500_from_except.py.txt", routes / "auth.py")

    note = acceptance_nodes.the_server_hid_the_cause([RECEIVED_500], ACCESS_LINES_ONLY, tmp_path)

    assert "its error handler hides the cause" in note
    # The four handlers that answer the named constant from an `except` that logs nothing.
    for line in (121, 185, 210, 266):
        assert f"`service/app/routes/auth.py` line {line}" in note


def test_a_log_that_states_a_cause_asks_for_no_log_line():
    output = (FIXTURES / "a_traceback_behind_access_lines.txt").read_text(encoding="utf-8")

    assert acceptance_nodes.the_server_hid_the_cause([RECEIVED_500], suite.what_the_server_logged(output)) == ""


def test_the_note_that_the_cause_was_hidden_goes_once_the_log_states_it(tmp_path):
    from app.graph import fresh_evidence

    shown = "[AC-1] signs up: Received: 500" + acceptance_nodes.THE_SERVER_HID_THE_CAUSE

    assert fresh_evidence.without_a_hidden_cause_since_logged(shown, ACCESS_LINES_ONLY) == shown
    assert "hides the cause" not in fresh_evidence.without_a_hidden_cause_since_logged(
        shown, "sqlite3.OperationalError: no such table: users")
