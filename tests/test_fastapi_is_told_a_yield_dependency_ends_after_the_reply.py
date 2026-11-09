"""FastAPI products are told a dependency's teardown runs after the response is sent.

Measured on a held-out run: the product opened its database session in a
`yield` dependency and committed after the `yield`. Since FastAPI 0.118 that
code runs once the response has gone out, so a sign-up answered 201 and the
sign-in sent straight after it found no account - every hidden test that
signs in failed, while its unit tests (through `TestClient`, which waits for
the teardown) passed and fixers could not reproduce it. A required `Header()`
also answered a missing credential 422 instead of 401.
"""

from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_teardown_timing_and_its_two_ways_out_are_given():
    text = SEED_INSTRUCTIONS["fastapi"]
    assert "after `yield`" in text and "response has been sent" in text
    assert "Commit in the route before it" in text
    assert 'scope=\\"function\\"' in text or 'scope="function"' in text
    assert "`TestClient` waits for the teardown" in text


def test_a_missing_header_is_answered_401_not_422():
    text = SEED_INSTRUCTIONS["fastapi"]
    assert "`Header(None)`" in text and "422" in text and "401" in text


def test_the_rule_names_no_product_words():
    assert not BANNED.search(SEED_INSTRUCTIONS["fastapi"])


def test_pydantic_version_two_is_named_with_the_version_one_forms_that_fail_silently():
    """Measured on a held-out run: a request model defined Pydantic 1's `__get_validators__` on Pydantic 2, so its
    validators never ran; 25 unit tests got no `ValidationError` and every request answered 422."""
    text = SEED_INSTRUCTIONS["fastapi"]
    assert "Pydantic is version 2" in text and "@field_validator" in text
    assert "`__get_validators__`" in text and "`@validator`" in text and "`.dict()`" in text
