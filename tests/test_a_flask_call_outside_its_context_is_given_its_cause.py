"""A Flask service that fails with "Working outside of application context" is given the context rule as its cause.

Measured on one Flask run: the product did not start and the unit tests failed with this message 92 times over three
rounds; each fix rewrote the entry file or the tests and none was told the rule.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_the_missing_application_context_is_given_its_rule(tmp_path):
    contract.write(tmp_path, pack_named("python-flask-api"), "tasks-api", "Tasks")
    said = ("RuntimeError: Working outside of application context.\n This typically means that you attempted to use "
            "functionality that needed the current application.")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The unit tests fail.", severity="major", reproduction_steps="pytest",
        expected_behavior="pass", actual_behavior=said, affected_files=[], owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "app.app_context()" in defect.actual_behavior
