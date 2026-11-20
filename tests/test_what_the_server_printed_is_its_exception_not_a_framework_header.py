"""What the server printed for a failed request is the exception its stack trace names, not a framework's header line.

Measured on one run: an edge probe's `GET /notes/99999999999999999999` answered 500 on a FastAPI service on SQLite;
uvicorn printed "ERROR: Exception in ASGI application", then a traceback of about a hundred lines ending in
`OverflowError: Python int too large to convert to SQLite INTEGER`. The defect carried the header line alone, so the
Python pack's known cause for that error never attached and the fixers were not told what failed.
"""
from __future__ import annotations

import re

import pytest

from app.acceptance import edge_probe as ep
from app.acceptance import what_went_wrong
from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
OVERFLOW = "OverflowError: Python int too large to convert to SQLite INTEGER"
HEADER = "Exception in ASGI application"


def _an_asgi_500(library_frames: int) -> str:
    """What uvicorn prints for a request its application failed: the access line, its header, then the traceback."""
    frames = []
    for n in range(library_frames):
        frames += [f'  File "/srv/.venv/lib/python3.12/site-packages/starlette/layer{n}.py", line {n + 10}, in __call__',
                   "    await self.app(scope, receive, send)", "    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^"]
    return "\n".join([
        'INFO:     127.0.0.1:57106 - "GET /health HTTP/1.1" 200 OK',
        'INFO:     127.0.0.1:57138 - "GET /notes/99999999999999999999 HTTP/1.1" 500 Internal Server Error',
        f"ERROR:    {HEADER}",
        "Traceback (most recent call last):",
        *frames,
        '  File "/srv/notes_api/main.py", line 140, in get_note',
        '    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()',
        OVERFLOW,
        'INFO:     127.0.0.1:57140 - "GET /notes/abc HTTP/1.1" 422 Unprocessable Entity',
    ])


@pytest.mark.parametrize("library_frames", [3, 40], ids=["a short trace", "a trace longer than the lines read"])
def test_a_python_traceback_after_an_asgi_header_is_shown_as_its_exception(library_frames):
    printed = _an_asgi_500(library_frames)

    found = what_went_wrong.what_the_server_printed_for(printed, "/notes/99999999999999999999", "GET")

    assert found.startswith(OVERFLOW) and 'File "/srv/notes_api/main.py", line 140' in found
    assert HEADER not in found and len(found) <= 400


def test_a_javascript_runtime_s_error_is_shown_without_its_framework_s_header():
    printed = ("[Nest] 42  - 11/20/2026, 8:48:00 AM   ERROR [ExceptionsHandler] Internal server error\n"
               "TypeError: Cannot read properties of undefined (reading 'id')\n"
               "    at NotesService.find (/app/src/notes.service.ts:12:20)\n"
               "    at /app/node_modules/@nestjs/core/router/router-execution-context.js:46:28\n")

    found = what_went_wrong.what_the_server_printed(printed)

    assert found == ("TypeError: Cannot read properties of undefined (reading 'id') "
                     "(at NotesService.find (/app/src/notes.service.ts:12:20))")


def test_a_jvm_exception_is_shown_with_its_root_cause_and_without_the_servlet_header():
    printed = (
        "ERROR 1 --- [exec-1] dispatcherServlet : Servlet.service() threw exception\n"
        "org.springframework.dao.DataIntegrityViolationException: could not execute statement\n"
        "\tat org.springframework.orm.jpa.vendor.HibernateJpaDialect.convert(HibernateJpaDialect.java:276)\n"
        "\tat com.example.notes.NoteService.find(NoteService.java:31)\n"
        "Caused by: org.h2.jdbc.JdbcSQLDataException: Numeric value out of range\n"
        "\tat org.h2.message.DbException.getJdbcSQLException(DbException.java:518)\n"
        "\t... 44 more\n")

    found = what_went_wrong.what_the_server_printed(printed)

    assert "DataIntegrityViolationException: could not execute statement" in found
    assert "Caused by: org.h2.jdbc.JdbcSQLDataException: Numeric value out of range" in found
    assert "Servlet.service()" not in found


def test_a_framework_s_header_with_no_trace_is_still_shown():
    found = what_went_wrong.what_the_server_printed(f"INFO:     started\nERROR:    {HEADER}\n")

    assert found == f"ERROR: {HEADER}"


def test_an_edge_probe_defect_built_from_an_asgi_500_is_given_the_python_known_cause(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes", "Notes")
    case = {"method": "GET", "shown": "/notes/{id}", "path": "/notes/99999999999999999999",
            "what": "at id `99999999999999999999`", "made_through": ""}
    errors = ep.with_what_the_server_printed(
        [(case, {"kind": "server_error", "status": 500, "said": "Internal Server Error"})], _an_asgi_500(40))
    defect = ReportedDefect(description=ep.edge_description(errors), severity="major", reproduction_steps="send it",
                            expected_behavior="a status under 500",
                            actual_behavior="; ".join(f"`{c['method']} {c['shown']}` {c['what']} "
                                                      f"{ep.what_came_back(c, f)}" for c, f in errors),
                            affected_files=[], owner="backend")

    found = with_known_causes(tmp_path, [defect])[0].actual_behavior

    assert f"the server printed: {OVERFLOW}" in found
    assert KNOWN_CAUSE in found and "9223372036854775807" in found
    assert not BANNED.search(found)
