"""A Hono pack's guide says a handler returns what the context builds, and what the server says when one does not.

Measured on one run: the health handler was `function healthCheckHandler(c: Context): void { c.body('OK', ...) }` -
it built the answer and returned nothing. Every request then failed inside `@hono/node-server` with
`TypeError: res.body.getReader is not a function`, which names neither the handler nor the missing `return`; the
product never started across two sprint attempts.
"""
from __future__ import annotations

import re

import pytest

from app.graph.builder_facts import MOST_GUIDE_CHARACTERS
from app.stacks import packs  # noqa: F401 - registers the packs
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["node-hono-native-api", "node-hono-api"])
def test_the_guide_says_to_return_the_answer_and_names_the_server_s_error(name):
    guide = pack_named(name).guide
    assert "return c.json(" in guide and "res.body.getReader is not a function" in guide
    # Measured on a later run: `app.get('/health', () => ({ status: 'ok' }))` - a plain object, read by the server
    # as a response whose status is `ok`; every request failed with "Invalid status code: ok".
    assert "a plain object" in guide and "Invalid status code" in guide
    assert len(guide) <= MOST_GUIDE_CHARACTERS
    assert not BANNED.search(guide)
