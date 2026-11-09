"""A service that dies of an unhandled error part-way through the suite is one blocking defect, not one per criterion.

Measured on one run: two saves raced on one temp file, the second `rename` failed, the rejection went unhandled and
Node exited mid-suite; the same product measured 15 of 16 in one round and 3 of 16 in another, and every test after
the crash became a criterion defect whose fixer looked at its own route.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
OUTPUT = """Running 4 tests using 1 worker
  ok 1 [AC-1] creates a note
[WebServer] node:internal/fs/promises:1491
[WebServer] Error: ENOENT: no such file or directory, rename 'data/notes.json.tmp' -> 'data/notes.json'
[WebServer]     at async rename (node:internal/fs/promises:1491:10)
[WebServer] Node.js v24.22.1
  x 2 [AC-4] updates a note
"""


def _report(*outcomes):
    return SimpleNamespace(tests=[SimpleNamespace(name=n, outcome=o, message=m) for n, o, m in outcomes])


def test_a_crash_after_a_pass_with_later_connection_failures_is_recorded_with_its_trace():
    report = _report(("[AC-1] creates", "passed", ""),
                     ("[AC-4] updates", "failed", "apiRequestContext.put: read ECONNRESET"),
                     ("[AC-5] deletes", "failed", "apiRequestContext.post: connect ECONNREFUSED 127.0.0.1:50127"))
    found = suite.the_product_crashed_mid_suite(report, OUTPUT)
    assert found.startswith(suite.PRODUCT_CRASHED) and "rename 'data/notes.json.tmp'" in found and "2 later test(s)" in found
    assert not BANNED.search(acceptance_nodes.THE_PRODUCT_CRASHED)


def test_no_crash_line_no_pass_or_no_connection_failure_is_not_a_crash():
    gone = ("[AC-4] updates", "failed", "connect ECONNREFUSED 127.0.0.1:1")
    assert suite.the_product_crashed_mid_suite(_report(("[AC-1] a", "passed", ""), gone), "  ok 1\n  x 2\n") == ""
    assert suite.the_product_crashed_mid_suite(_report(gone), OUTPUT) == ""
    assert suite.the_product_crashed_mid_suite(
        _report(("[AC-1] a", "passed", ""), ("[AC-4] b", "failed", "Expected: 200 Received: 404")), OUTPUT) == ""


def test_the_round_raises_one_blocking_defect_and_drops_the_criteria_it_took_down():
    source = inspect.getsource(acceptance_nodes.failing_due_defects)
    assert "never_started.startswith(suite.PRODUCT_CRASHED)" in source and "description=THE_PRODUCT_CRASHED" in source
    assert "crashed = the_product_crashed_mid_suite(report, output)" in inspect.getsource(suite.run)
