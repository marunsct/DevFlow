"""What a failing command printed is shown without its repeated lines, its stated errors first.

Measured on one PHP run: every route answered 500, and the defect's "what the last failing command printed" was forty
lines of the development server's access log - "Accepted", "Closing", a new port each time - with the error that
caused the 500s cut off above them. The fixer did not find the shared cause in two rounds.
"""
from __future__ import annotations

import json

from app.observability import transcript

ACCESS = [f"[WebServer] [Thu Nov 19 23:30:{n % 60:02d} 2026] 127.0.0.1:{36000 + n} {'Accepted' if n % 2 else 'Closing'}"
          for n in range(120)]
ERROR = "[WebServer] PHP Fatal error:  Uncaught PDOException: SQLSTATE[HY000]: unable to open database file in /app/src/Store.php:14"


def _shown(lines, limit=40):
    return transcript._last_lines(json.dumps({"stdout": "\n".join(lines), "returncode": 1}), limit)  # noqa: SLF001


def test_the_error_above_the_access_log_is_shown():
    said = _shown(["> playwright test", ERROR, *ACCESS])

    assert "unable to open database file" in said
    assert said.count("Accepted") + said.count("Closing") <= 4, said


def test_lines_differing_only_in_numbers_are_kept_once():
    said = _shown([f"retrying connection attempt {n}" for n in range(50)])

    assert said.count("retrying connection attempt") == 1
    assert "49 more line(s) like the ones above" in said


def test_different_lines_are_all_kept():
    lines = ["one", "two", "three"]
    assert _shown(lines) == "one\ntwo\nthree"
