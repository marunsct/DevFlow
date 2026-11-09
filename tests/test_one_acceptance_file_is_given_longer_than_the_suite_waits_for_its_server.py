"""One acceptance file's run is given longer than its suite waits for the product's server.

Measured on one run: the product never answered its readiness request, the
pack's suite waits 60 seconds for the server, and one file's run was limited
to 60 seconds too. The sandbox stopped each run a moment before the runner
could say the server never came up, so the check that skips the other files
once the product has not started (`per_file.each_file`) never saw it, and
each file waited out its minute after every write a fixer made.
"""
from __future__ import annotations

from app.stacks import packs  # noqa: F401 - registers the packs
from app.stacks import pack_named
from app.tools import sandbox


def test_a_service_pack_carries_the_wait_its_suite_gives_the_server():
    assert pack_named("node-hono-native-api").server_wait_ms == 60_000


def test_one_file_s_limit_is_longer_than_that_wait(monkeypatch):
    pack = pack_named("node-hono-native-api")
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: (pack, {}))

    assert sandbox.timeout_for("probe", "/nowhere") > pack.server_wait_ms / 1000
    assert sandbox.timeout_for("install", "/nowhere") == sandbox.timeout_for("install", None)
