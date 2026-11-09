"""The Hono pack's kept start file hands `DATA_DIR` to the app factory, which one that takes none ignores.

Measured on a held-out run: the design made the factory `createApp(dataDir: string)`; the start file called it with
nothing, so the service crashed at start (`path.join(undefined, ...)`) and the locked suite ran no test at all.
"""
from __future__ import annotations

from app.stacks.packs import node_hono_native_api as pack


def test_the_factory_is_called_with_the_data_directory():
    assert "await factory(process.env.DATA_DIR)" in pack.MAIN
    assert "(dataDir?: string) => Hono | Promise<Hono>" in pack.MAIN


def test_a_factory_with_no_argument_is_still_served():
    assert "exported.createApp ?? exported.default" in pack.MAIN
    assert "await factory(" in pack.MAIN and "await factory()" not in pack.MAIN
