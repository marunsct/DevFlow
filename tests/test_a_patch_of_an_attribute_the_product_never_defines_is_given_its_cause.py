"""A unit test that patches an attribute the product never defines is told so, with what to patch instead.

Measured on one FastAPI run: tests used `patch.object(app.state, 'db_path', ...)` for a name the product did not define;
every test failed in its fixture with `does not have the attribute 'db_path'` (14 repeats over three rounds) and the fixers
rewrote the product's startup, not the tests.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes
from app.stacks.packs import _python


def test_a_missing_attribute_is_given_the_patch_rule(tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "tasks-api", "Tasks")
    said = ("AttributeError: <starlette.datastructures.State object at 0x7f05> does not have the attribute 'db_path'")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The unit tests fail.", severity="major", reproduction_steps="pytest", expected_behavior="pass",
        actual_behavior=said, affected_files=[], owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "create=True" in defect.actual_behavior


def test_the_added_words_use_none_of_the_banned_ones():
    cause = _python.PYTHON_KNOWN_ERRORS["does not have the attribute"]

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", cause, re.I)
