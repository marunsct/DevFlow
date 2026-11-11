"""A finding that a test broke itself quotes the runner's reason, not only where it stopped.

Measured on one run: every test of a file asked for a fixture nothing defined; the finding read only "failed on setup
with "file .../test_items.py, line 8"", the reason three lines down, and the writer sent back twice did not fix what
it was never told.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import junit, suite
from app.stacks import contract, pack_named

SETUP_ERROR = (
    'failed on setup with "file /w/tasks-api/acceptance/test_items.py, line 8\n'
    "  def test_ac3_create_item(auth_token, base_url):\n"
    "E       fixture 'auth_token' not found\n"
    ">       available fixtures: base_url, service, tmp_path\n"
)


def test_the_reason_line_is_quoted(tmp_path):
    contract.write(tmp_path, pack_named("python-flask-api"), "tasks-api", "Tasks")
    result = SimpleNamespace(report=SimpleNamespace(tests=[
        junit.TestResult(name="test_ac3_create_item", outcome="failed", message=SETUP_ERROR)]), problem="", ran=True)

    found = suite.tests_that_broke_themselves(tmp_path, result)

    assert len(found) == 1
    assert "fixture 'auth_token' not found" in found[0]
    assert "test_items.py, line 8" in found[0]
