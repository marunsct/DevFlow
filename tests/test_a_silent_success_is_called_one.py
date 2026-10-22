"""An exit code of 0 with nothing printed is named as a success.

One run's `specialist_testing_4` ran `npx playwright install chromium` with the
browser already cached. It exited 0 and printed nothing, and the stage sent the
identical command four more times - the first repeat before any repeat note
existed - until the harness refused it.
"""

from __future__ import annotations

import inspect

from app.tools import sandbox
from app.tools.sandbox import _a_silent_success


def test_a_silent_exit_zero_is_called_a_success():
    note = _a_silent_success({"stdout": "", "stderr": "", "returncode": "0"})

    assert "which is success" in note
    assert "Running it again will print nothing again" in note


def test_whitespace_is_still_nothing():
    assert _a_silent_success({"stdout": "\n", "stderr": "  ", "returncode": 0})


def test_output_gets_no_note():
    assert _a_silent_success({"stdout": "added 3 packages", "stderr": "", "returncode": "0"}) == ""


def test_a_failure_gets_no_note():
    assert _a_silent_success({"stdout": "", "stderr": "", "returncode": "1"}) == ""


def test_a_refusal_gets_no_note():
    assert _a_silent_success({"error": "not permitted"}) == ""


def test_it_is_attached_when_no_repeat_note_is():
    """A repeat keeps its own, stronger note; the first run gets this one."""
    source = inspect.getsource(sandbox)

    assert ") or _a_silent_success(outcome)" in source
