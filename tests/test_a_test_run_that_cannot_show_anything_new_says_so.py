"""A test command that answers as it did last time, with no file changed since, says re-running cannot show anything new.

Measured on a gate run: a fixer ran one test command twice in a row and
another three times, each with the same result, reasoning 4,000-20,000 tokens
"to reproduce the failure" between runs. The guard against a repeated call
waits for four in a row.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from unittest import mock

from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
COMMAND = ["python", "-m", "pytest", "acceptance", "-q"]
RESULT = {"stdout": "===== 5 passed, 1 failed in 0.42s =====\n"}


def _ledger(tmp_path, passed, tests, seconds_ago=60):
    at = datetime.fromtimestamp(time.time() - seconds_ago, timezone.utc).isoformat()
    return [{"command": COMMAND, "working_directory": "items-api", "passed": passed, "tests": tests, "at": at}]


def _note(tmp_path, ledger):
    with mock.patch.object(sandbox, "read_execution_ledger", lambda root, by_the_agents=True: ledger), \
         mock.patch.object(sandbox, "_where_it_ran", lambda directory: "items-api"):
        return sandbox._fewer_pass_than_last_time(str(tmp_path), COMMAND, "items-api", RESULT)


def test_the_same_counts_with_nothing_changed_say_a_rerun_shows_nothing_new(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    old = time.time() - 600
    os.utime(tmp_path / "main.py", (old, old))

    note = _note(tmp_path, _ledger(tmp_path, 5, 6))

    assert "5 of 6 passed" in note and "cannot show anything new" in note
    assert not BANNED.search(note)


def test_a_file_changed_since_or_other_counts_say_nothing_of_the_kind(tmp_path):
    (tmp_path / "main.py").write_text("x = 2\n")
    assert _note(tmp_path, _ledger(tmp_path, 5, 6)) == ""
    old = time.time() - 600
    os.utime(tmp_path / "main.py", (old, old))
    assert _note(tmp_path, _ledger(tmp_path, 4, 6)) == ""
