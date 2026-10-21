"""A release is held back until the product's README says how to run it and what it serves (plan PN.2).

Released products were handed over with CI files and no word on how to start
them. Behind `RELEASE_DOCS_REQUIRED`, off until measured: held back like a
failing criterion while attempts remain, then recorded as a gap.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from unittest import mock

import pytest

from app.acceptance import interface_contract
from app.graph import delivery
from app.stacks import contract, release_docs

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"RELEASE_DOCS_REQUIRED": "on"}


@pytest.fixture
def product(tmp_path, monkeypatch):
    pack = SimpleNamespace(install=(("pip", "install", "-e", "."),), unit_test=("pytest", "tests/unit"),
                           acceptance_test=("pytest", "tests/acceptance"), entrypoints=(), entrypoint="")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    (tmp_path / "app").mkdir()
    interface_contract.record_at_lock(tmp_path, ["AC-1 GET /items -> 200", "AC-2 DELETE /items/{id} -> 204"])
    return tmp_path


def test_no_readme_is_a_lack(product):
    with mock.patch.dict(os.environ, ON):
        lacks = release_docs.what_the_handoff_lacks(product)
    assert len(lacks) == 1 and "no README" in lacks[0]
    assert not BANNED.search(lacks[0])


def test_a_readme_with_no_way_to_run_it_and_routes_unnamed_lacks_both(product):
    (product / "app" / "README.md").write_text("# Items\n\nA service for items.\n\n- GET /items lists them\n")
    with mock.patch.dict(os.environ, ON):
        lacks = release_docs.what_the_handoff_lacks(product)
    assert any("says nowhere how to run" in lack and "pip install -e ." in lack for lack in lacks)
    routes = next(lack for lack in lacks if "summarises these routes" in lack)
    assert "DELETE /items/{id}" in routes and "GET /items" not in routes
    assert not any(BANNED.search(lack) for lack in lacks)


def test_a_complete_readme_lacks_nothing_and_off_nothing_is_checked(product):
    (product / "app" / "README.md").write_text(
        "# Items\n\nRun `sh start.sh`; test with `pytest tests/unit`.\n\n"
        "| GET | /items | the list |\n| DELETE | /items/:id | removes one, 204 |\n")
    with mock.patch.dict(os.environ, ON):
        assert release_docs.what_the_handoff_lacks(product) == []
    (product / "app" / "README.md").unlink()
    with mock.patch.dict(os.environ, {"RELEASE_DOCS_REQUIRED": ""}):
        assert release_docs.what_the_handoff_lacks(product) == []


def _release(root, attempts):
    return delivery.release(
        {"repository": SimpleNamespace(root_path=str(root)), "release_attempts": attempts},
        {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True),
    )


def test_the_release_holds_back_while_attempts_remain_then_records_a_gap(product, monkeypatch):
    from app.analysis import integration_checks

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: [])
    with mock.patch.dict(os.environ, ON):
        held = _release(product, 0)
        assert held["stage"] == "technical_lead"
        assert "no README" in held["revision_comments"][-1]
        released = _release(product, delivery.MAX_RELEASE_ATTEMPTS)
    assert released["stage"] != "technical_lead"
    assert any("no README" in str(gap) for gap in released.get("completion_gaps") or [])
