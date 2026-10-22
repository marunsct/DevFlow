"""A release is held back until the product's README says how to run it and what it serves (plan PN.2).

Released products were handed over with CI files and no word on how to start
them. Behind `RELEASE_DOCS_REQUIRED`, off until measured: held back like a
failing criterion while attempts remain, then recorded as a gap.
"""
from __future__ import annotations

import inspect
import os
import re
from types import SimpleNamespace
from unittest import mock

import pytest

from app.acceptance import interface_contract
from app.graph import delivery, workflow
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


def _no_checks(monkeypatch):
    from app.analysis import integration_checks

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: [])


def test_the_release_writes_what_the_harness_knows_and_goes_on(product, monkeypatch):
    _no_checks(monkeypatch)
    with mock.patch.dict(os.environ, ON):
        released = _release(product, 0)
    assert released["stage"] != "technical_lead"
    assert (product / "app" / "README.md").is_file()


def test_the_release_holds_back_what_it_cannot_write_while_attempts_remain_then_records_a_gap(product, monkeypatch):
    _no_checks(monkeypatch)
    # No pack: the harness knows no command to write.
    monkeypatch.setattr(contract, "the_pack", lambda root: None)
    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    with mock.patch.dict(os.environ, ON):
        held = _release(product, 0)
        assert held["stage"] == "technical_lead"
        assert "no README" in held["revision_comments"][-1]
        released = _release(product, delivery.MAX_RELEASE_ATTEMPTS)
    assert released["stage"] != "technical_lead"
    assert any("no README" in str(gap) for gap in released.get("completion_gaps") or [])


def test_what_the_harness_knows_is_written_into_the_readme_and_nothing_is_left_to_ask(product):
    (product / "app" / "start.sh").write_text("exec serve\n")
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(product) == ["app/README.md"]
        assert release_docs.what_the_handoff_lacks(product) == []
        assert release_docs.complete_the_handoff(product) == [], "nothing is added twice"
    text = (product / "app" / "README.md").read_text()
    assert "pip install -e ." in text and "sh start.sh" in text and "| DELETE | `/items/{id}` | 204 |" in text
    assert not BANNED.search(text)


def test_an_own_readme_keeps_its_words_and_gains_only_what_it_lacks(product):
    (product / "app" / "README.md").write_text("# Items\n\nRun `sh start.sh`.\n\n- GET /items lists them\n")
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(product)
    text = (product / "app" / "README.md").read_text()
    assert text.startswith("# Items\n\nRun `sh start.sh`.") and "Running it" not in text
    assert "DELETE | `/items/{id}`" in text and "| GET | `/items`" not in text


def test_off_the_readme_is_not_touched(product):
    with mock.patch.dict(os.environ, {"RELEASE_DOCS_REQUIRED": ""}):
        assert release_docs.complete_the_handoff(product) == []
    assert not (product / "app" / "README.md").exists()


def test_a_route_with_a_trailing_slash_and_a_project_named_like_a_record_are_read_as_documented(tmp_path, monkeypatch):
    """`POST /items/` written in the README stayed missing, and a project called `book-reviews` had every
    document left out: each sent the release back twice for what it already had."""
    pack = SimpleNamespace(install=(("pip", "install", "."),), unit_test=("pytest",), acceptance_test=("pytest",),
                           entrypoints=(), entrypoint="")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "book-reviews"}))
    (tmp_path / "book-reviews").mkdir()
    interface_contract.record_at_lock(tmp_path, ["AC-1 POST /items/ -> 201"])
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(tmp_path)
        assert release_docs.what_the_handoff_lacks(tmp_path) == []


def test_the_lead_is_told_why_the_release_was_held_back():
    """The hold hands on with no milestone plan, so the lead planned afresh and the planning request
    never read the comments: two re-sprints were told nothing."""
    source = inspect.getsource(workflow)
    lead = source[source.index("    def technical_lead_node("):]
    lead = lead[:lead.index("\n    def ", 10)]
    assert "Why the release was held back" in lead and 'state.get("release_attempts")' in lead


def test_a_root_readme_names_the_project_directory_and_a_pack_without_a_start_script_names_its_start(tmp_path, monkeypatch):
    pack = SimpleNamespace(install=(("npm", "install"),), unit_test=("npm", "test"), acceptance_test=("npm", "run", "test:acceptance"),
                           entrypoints=(), entrypoint="", language="typescript", kept_scripts={"start": "node dist/main.js"})
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "shop"}))
    (tmp_path / "shop").mkdir()
    (tmp_path / "README.md").write_text("# Shop\n")
    interface_contract.record_at_lock(tmp_path, ["AC-1 GET /items -> 200"])
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(tmp_path) == ["README.md"]
    text = (tmp_path / "README.md").read_text()
    assert "From `shop/`:" in text and "npm start" in text
