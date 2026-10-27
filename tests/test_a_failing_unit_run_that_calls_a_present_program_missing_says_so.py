"""A failing unit run that names a program here as missing says it is here, in the defect a fix reads.

Measured on one run: the product's unit tests spawned children with a working
directory given relative to the wrong folder, and Node reported
`spawn /bin/sh ENOENT`. The harness's own unit run became the defect, which
did not carry the note a stage's own command gets for the same output, and two
fixes in a row concluded "the test suite spawns /bin/sh and /usr/bin/node,
which are not available in this environment", changed nothing, and the sprint
was planned again twice.
"""
from __future__ import annotations

import shutil

from app.graph.workflow import _the_unit_tests_fail
from test_graph_routing import _milestone


def test_a_present_program_reported_missing_is_said_to_be_here():
    shell = shutil.which("sh")
    output = (f"not ok 1 - sh wrapper starts server\n  Error: spawn {shell} ENOENT\n"
              "  failureType: 'uncaughtException'\nfail 1\n")

    defect = _the_unit_tests_fail(_milestone("testing", "backend"), output)

    assert f"'{shell}' exists in this environment" in defect.description
    assert "working directory that does not exist" in defect.description


def test_a_failure_that_names_no_missing_program_has_no_such_note():
    defect = _the_unit_tests_fail(_milestone("testing", "backend"), "FAIL store.test.ts > keeps ids\n")

    assert "exists in this environment" not in defect.description
