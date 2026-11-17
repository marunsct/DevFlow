"""A service that dies of an unhandled error part-way through the suite is one blocking defect, not one per criterion.

Measured on one run: two saves raced on one temp file, the second `rename` failed, the rejection went unhandled and
Node exited mid-suite; the same product measured 15 of 16 in one round and 3 of 16 in another, and every test after
the crash became a criterion defect whose fixer looked at its own route.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.acceptance.criteria import number
from app.acceptance.junit import tags_in
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
    assert found.startswith("The product crashed while the acceptance suite ran")
    assert "rename 'data/notes.json.tmp'" in found and "2 later test(s)" in found
    assert not BANNED.search(acceptance_nodes.THE_PRODUCT_CRASHED)


def test_no_crash_line_no_pass_or_no_connection_failure_is_not_a_crash():
    gone = ("[AC-4] updates", "failed", "connect ECONNREFUSED 127.0.0.1:1")
    assert suite.the_product_crashed_mid_suite(_report(("[AC-1] a", "passed", ""), gone), "  ok 1\n  x 2\n") == ""
    assert suite.the_product_crashed_mid_suite(_report(gone), OUTPUT) == ""
    assert suite.the_product_crashed_mid_suite(
        _report(("[AC-1] a", "passed", ""), ("[AC-4] b", "failed", "Expected: 200 Received: 404")), OUTPUT) == ""


JUNIT = ('<testsuite tests="3"><testcase classname="c" name="[AC-1] creates a note"/>'
         '<testcase classname="c" name="[AC-2] updates a note"><failure message="{gone}">{gone}</failure></testcase>'
         '<testcase classname="c" name="[AC-3] lists the notes"><failure message="{other}">{other}</failure></testcase>'
         '</testsuite>')


def test_the_round_raises_one_blocking_defect_and_drops_the_criteria_it_took_down(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Create a note\n- Update a note\n- List the notes\n"))
    project = tmp_path / "notes"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "test_x.py").write_text("def test_x(): pass\n")
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["pytest"], "report": "r.xml"}))
    suite.lock(tmp_path)

    def the_suite_in_the_sandbox(argv, category, where):
        (project / "r.xml").write_text(JUNIT.format(gone="apiRequestContext.put: read ECONNRESET",
                                                    other="Expected: 3 Received: 2"))
        return {"returncode": "1", "stdout": OUTPUT, "stderr": ""}

    suite.run(tmp_path, runner=the_suite_in_the_sandbox)
    defects = acceptance_nodes.failing_due_defects({"repository": SimpleNamespace(root_path=str(tmp_path))}, [])

    crashed = [d for d in defects if d.severity == "blocking"]
    assert len(crashed) == 1 and "rename 'data/notes.json.tmp'" in crashed[0].actual_behavior
    assert [tag for d in defects for tag in tags_in(d.description)] == ["AC-3"]
