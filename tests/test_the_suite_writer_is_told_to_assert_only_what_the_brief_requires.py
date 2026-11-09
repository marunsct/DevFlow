"""The acceptance writer is told to assert only what the brief or the interface contract says.

Measured on one run: seven of the eight gaps the release recorded were locked tests asserting the exact text of an
error body ("invalid JSON body", "item not found") where the brief and contract required only the status code. The
product was right; the suite, locked, could not be satisfied without guessing the specification's wording.
"""
from __future__ import annotations

import re

from app.acceptance import requests as acceptance_requests

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _request(tmp_path) -> str:
    criteria = acceptance_requests.suite.criteria(tmp_path)
    return acceptance_requests.build_author_request(tmp_path, criteria)["messages"][-1]["content"]


def test_the_request_tells_the_writer_to_assert_no_more_than_the_brief_requires(tmp_path):
    text = _request(tmp_path)

    rule = text.split("- A test checks what the brief or the interface contract says, and no more.")[1].split("\n- ")[0]
    assert "Where they give no wording for an error or a message" in rule
    assert "the status, the shape" in rule and "wording nobody required" in rule


def test_the_rule_uses_none_of_the_banned_words(tmp_path):
    text = _request(tmp_path)
    rule = text.split("- A test checks what the brief or the interface contract says")[1].split("\n- ")[0]

    assert not BANNED.search(rule)
