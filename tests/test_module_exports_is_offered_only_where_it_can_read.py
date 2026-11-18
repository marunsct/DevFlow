"""`module_exports` is offered only on stacks whose packages it reads.

Measured on a PHP run: asked for `Slim\\Factory\\AppFactory`, installed under `vendor/`, it answered "not installed in this
project ... Install it first", and the builder was sent the wrong way.
"""
from __future__ import annotations

import pytest

from app.analysis.package_exports import exports_tools
from app.stacks import contract, pack_named


@pytest.mark.parametrize("pack, offered", [
    ("php-slim-api", False), ("rust-axum-api", False), ("node-hono-api", True), ("python-http-api", True),
])
def test_the_tool_is_offered_by_the_stack_s_language(tmp_path, monkeypatch, pack, offered):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    contract.write(tmp_path, pack_named(pack), "svc", "Svc")

    assert bool(exports_tools(tmp_path)) is offered


def test_a_project_without_a_pack_keeps_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")

    assert exports_tools(tmp_path)
