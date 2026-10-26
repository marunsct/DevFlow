"""A service pack whose kept start file calls `createApp()` says the factory returns the application, not a Promise.

Measured on a small-model run: `createApp` was made `async` to load the data first; the kept start file then served
the `fetch` of a Promise and every request answered 500 for two sprint attempts.
"""
from __future__ import annotations

import re

import pytest

from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["node-hono-native-api", "node-hono-api", "node-http-api"])
def test_the_guide_says_the_factory_is_not_async(name):
    pack = pack_named(name)
    start = " ".join(text for path, text in pack.files.items() if "createApp()" in text and "test" not in path)
    assert "createApp()" in start
    assert "never a Promise" in pack.guide and "not `async`" in pack.guide
    assert not BANNED.search(pack.guide)


def test_every_service_pack_guide_reaches_the_builders_whole():
    from app.graph import builder_facts

    for name in ("node-hono-native-api", "node-hono-api", "node-http-api"):
        assert len(pack_named(name).guide) <= builder_facts.MOST_GUIDE_CHARACTERS
