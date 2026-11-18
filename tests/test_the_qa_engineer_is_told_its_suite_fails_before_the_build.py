"""The QA engineer, writing the suite before anything is built, is told its tests fail until then.

Measured on one run: it ran its suite against the unbuilt product, saw every test fail, and spent 59 minutes and 51
replies editing tests to pass; the family's other runs wrote theirs in about 8.
"""
from __future__ import annotations

import re

from app.acceptance import requests as acceptance_requests
from app.acceptance.criteria import number
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = "# Brief\n## Features\n- Add a note\n- List notes\n"


def _the_request(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    request = acceptance_requests.build_author_request(tmp_path, number(BRIEF), None, brief=BRIEF)
    return request["messages"][-1]["content"]


def test_before_the_build_it_is_told_failing_tests_are_expected(tmp_path):
    said = _the_request(tmp_path)

    assert "every test of a feature fails: that is expected, and never a reason to change a test" in said
    assert not BANNED.search(acceptance_requests.NOT_BUILT_SO_IT_FAILS)
