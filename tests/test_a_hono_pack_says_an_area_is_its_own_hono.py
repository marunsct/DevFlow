"""A Hono pack's guide says an area's routes are their own `new Hono()`: Hono has no `Router`.

Measured on one run: the draft wrote `import { Router } from 'hono/router'` and `new Router()` the way Express is
written; Node stopped at start with "The requested module 'hono/router' does not provide an export named 'Router'",
and two fixes were each refused or reverted for importing a `Router` from `hono` in turn.
"""
from __future__ import annotations

import re

import pytest

from app.graph.builder_facts import MOST_GUIDE_CHARACTERS
from app.stacks import packs  # noqa: F401 - registers the packs
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["node-hono-native-api", "node-hono-api"])
def test_the_guide_says_there_is_no_router(name):
    guide = pack_named(name).guide
    assert "new Hono()" in guide and "there is no `Router`" in guide
    assert len(guide) <= MOST_GUIDE_CHARACTERS
    assert not BANNED.search(guide)
