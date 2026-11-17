"""QA is shown the acceptance smoke test that passed at setup, as the shape its tests copy.

One run's QA spent 149 minutes and 182 calls writing its suite from nothing,
a third of the calls malformed or refused.
"""

from __future__ import annotations

import re

from app.acceptance import requests
from app.acceptance.criteria import Criterion
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: Where the request shows the example.
SHOWN = "--- A test that ran and passed in this project's own runner ---"


def _the_author_s_request(root) -> str:
    return requests.build_author_request(root, [Criterion("AC-1", "a note is kept", "brief")])["messages"][0]["content"]


def test_a_pack_s_acceptance_smoke_test_is_shown_and_its_unit_smoke_test_is_not(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")

    told = _the_author_s_request(tmp_path)

    shown = told[told.index(SHOWN):]
    shown = shown[:shown.index("```\n\n") + 3]
    assert "test('the running service answers'" in shown
    assert "createApp" not in shown
    assert not BANNED.search(shown[:shown.index("```")])


def test_a_proven_setup_s_kept_example_is_shown_in_place_of_the_pack_s(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes",
                   extra={"setup": {"acceptance_example": "it('[AC-0] starts', () => {})"}})

    told = _the_author_s_request(tmp_path)

    assert "it('[AC-0] starts'" in told[told.index(SHOWN):]
    assert "the running service answers" not in told


def test_no_example_leaves_the_request_without_one(tmp_path):
    assert SHOWN not in _the_author_s_request(tmp_path)
