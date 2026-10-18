"""A fixer of a service product is told a missing database server is no reason to change nothing (Initiative K.2).

Measured live: the specification named PostgreSQL, and three fixes of three
criteria each ended "changed nothing: no PostgreSQL server is available, an
environmental constraint", while the product could run on an embedded file.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph.workflow import _the_database_section
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_service_product_s_fixer_is_told(monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(kind="fullstack"), {}))

    said = _the_database_section("/work")

    assert "embedded file database under the directory named by `DATA_DIR`" in said
    assert "never a reason to change nothing" in said
    assert not BANNED.search(said)


def test_a_product_with_no_service_is_not(monkeypatch):
    for kind in ("browser_app", "cli", "library"):
        monkeypatch.setattr(contract, "the_pack", lambda root, kind=kind: (SimpleNamespace(kind=kind), {}))
        assert _the_database_section("/work") == ""


def test_no_pack_and_no_root_say_nothing(monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: None)

    assert _the_database_section("/work") == "" and _the_database_section(None) == ""


def test_the_fix_request_carries_it():
    import inspect

    from app.graph import workflow

    assert '_the_database_section(state["repository"].root_path)' in inspect.getsource(workflow)
