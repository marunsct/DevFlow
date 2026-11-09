"""A locked test whose own line raises `TypeError: unhashable type` fails by its own code.

Measured on a small-model run: QA wrote `httpx.post(url, json={{"title": ""}})` - double braces carried over from a
template, which Python reads as a set holding a dict. The line raised before any request was made, so five locked
criteria could not pass whatever was built; each round handed them to the product's fixers, and the sprint spent two
hours on them while the hidden tests passed 10 of 10.
"""
from __future__ import annotations

import re

import pytest

from app.stacks.packs import _python


def _broke_itself(message):
    return any(re.search(pattern, message, re.I | re.M) for pattern in _python.TEST_BUGS)


@pytest.mark.parametrize("message", [
    "TypeError: unhashable type: 'dict'\nbase_url = 'http://127.0.0.1:59249'",
    "acceptance/test_ac20.py:14: TypeError: unhashable type: 'list'",
    "TypeError: unhashable type: 'set'",
])
def test_an_unhashable_member_in_the_test_s_own_line_is_the_test_s_bug(message):
    assert _broke_itself(message)


@pytest.mark.parametrize("message", [
    "assert 409 == 201\n + where 409 = <Response [409 Conflict]>.status_code",
    "KeyError: 'token'",
    "TypeError: 'NoneType' object is not subscriptable",
    "ImportError: cannot import name 'app' from 'tasks_api'",
])
def test_the_product_s_answers_stay_the_product_s(message):
    assert not _broke_itself(message)


def test_every_python_pack_carries_it():
    from app.stacks.packs import ALL_PACKS

    for pack in ALL_PACKS:
        if pack.language == "python" and pack.kind == "http_api":
            assert any("unhashable" in pattern for pattern in pack.test_bugs), pack.name
