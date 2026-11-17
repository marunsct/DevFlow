"""An exit code of 0 with nothing printed is named as a success.

One run's `specialist_testing_4` ran `npx playwright install chromium` with the
browser already cached. It exited 0 and printed nothing, and the stage sent the
identical command four more times - the first repeat before any repeat note
existed - until the harness refused it.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import SandboxExecutor

COMMAND = ["npx", "playwright", "install", "chromium"]


def _the_note(tmp_path, monkeypatch, answered: dict) -> str:
    """The note on a stage's first run of `COMMAND`, which the container answered `answered`."""
    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(lambda cls, *args, **kwargs: dict(answered)))
    return str(SandboxExecutor.execute(COMMAND, str(tmp_path), "testing_specialist").get("note") or "")


@pytest.mark.parametrize("answered", [
    {"stdout": "", "stderr": "", "returncode": "0"},
    {"stdout": "\n", "stderr": "  ", "returncode": 0},
])
def test_a_silent_exit_zero_is_called_a_success(tmp_path, monkeypatch, answered):
    note = _the_note(tmp_path, monkeypatch, answered)

    assert "which is success" in note and "Running it again will print nothing again" in note


@pytest.mark.parametrize("answered", [
    {"stdout": "added 3 packages", "stderr": "", "returncode": "0"},
    {"stdout": "", "stderr": "", "returncode": "1"},
    {"error": "not permitted"},
])
def test_output_a_failure_or_a_refusal_is_not_called_one(tmp_path, monkeypatch, answered):
    assert "which is success" not in _the_note(tmp_path, monkeypatch, answered)
