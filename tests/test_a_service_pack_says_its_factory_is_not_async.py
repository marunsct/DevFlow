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


def test_the_native_pack_s_start_file_serves_a_factory_that_returns_a_promise():
    pack = pack_named("node-hono-native-api")
    main = pack.files["src/main.ts"]
    assert "const app = await factory();" in main and "fetch: app.fetch" in main
    assert "createApp().fetch" not in main
    assert "await (await createApp()).request('/health')" in pack.smoke_files["test/scaffold-smoke.test.ts"]


def test_the_native_pack_s_start_file_takes_the_named_factory_or_the_default_export():
    main = pack_named("node-hono-native-api").files["src/main.ts"]
    assert "import * as entry from './app.ts';" in main
    assert "exported.createApp ?? exported.default" in main


def test_the_guide_says_the_factory_is_a_named_export_with_no_parameters():
    guide = pack_named("node-hono-native-api").guide
    assert "not `export default`" in guide and "takes no parameters" in guide and "from the environment" in guide
