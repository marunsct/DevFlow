"""A Python defect that says a call has the wrong arguments is given the cause: tests and code disagree on a signature.

Measured on three held-out runs: the unit tests and the code they test disagreed about a function's parameters
(connection first in some tests, by keyword in others, neither in the product's own caller). Each fix changed the
function to suit some tests, broke the rest and was reverted; the sprint was planned again until the run failed.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PACKS = ("python-http-api", "python-flask-api", "python-library", "python-cli")


def _defect(text):
    return ReportedDefect(description=f"The unit tests fail. It says: {text}", severity="major",
                          reproduction_steps="pytest", expected_behavior="they pass", actual_behavior=text,
                          affected_files=[], owner="backend")


def test_every_python_pack_knows_the_error():
    for name in PACKS:
        known = pack_named(name).known_errors
        assert "positional argument" in known and "unexpected keyword argument" in known, name


def test_a_python_project_s_wrong_argument_count_is_given_its_cause_once(tmp_path):
    contract.write(tmp_path, pack_named("python-flask-api"), "items", "Items")
    first = with_known_causes(tmp_path, [_defect("TypeError: create_account() takes 2 positional arguments but 3 were given")])
    assert KNOWN_CAUSE in first[0].actual_behavior and "product's own code calls the function" in first[0].actual_behavior
    assert not BANNED.search(first[0].actual_behavior)
    assert with_known_causes(tmp_path, first)[0].actual_behavior.count(KNOWN_CAUSE) == 1
    other = with_known_causes(tmp_path, [_defect("AssertionError: assert 500 == 401")])
    assert KNOWN_CAUSE not in other[0].actual_behavior


def test_a_missing_argument_and_an_unexpected_keyword_get_it_too(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "items", "Items")
    for text in ("TypeError: f() missing 1 required positional argument: 'conn'",
                 "TypeError: f() got an unexpected keyword argument 'conn'"):
        assert KNOWN_CAUSE in with_known_causes(tmp_path, [_defect(text)])[0].actual_behavior
