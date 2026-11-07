"""Behind `SETUP_SCOPE_GUARD`: a layered setup stage writes the framework files it was asked for, its declaration,
smoke tests, manifests and test configuration - not the product's own code (docs/measuring.md M6).

Measured on a stack no pack covers: asked for four framework files, the setup stage wrote the whole product before
the specification's builders ran; nothing changed after the lock and the product shipped broken (hidden 0 of 9).
"""
from __future__ import annotations

import re

import pytest

from app.stacks.custom_setup import record_the_setup_s_scope
from app.tools import repository


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    import app.observability.transcript as transcript

    monkeypatch.setattr(transcript, "_stage_from_config", lambda default="": "stack_setup_0")
    monkeypatch.setenv("SETUP_SCOPE_GUARD", "on")
    record_the_setup_s_scope(tmp_path, "notes-api", {"notes_api/main.py": "the app", "start.sh": "start"})
    return tmp_path


def _refusal(root, path):
    return repository._beyond_the_setup_s_files(root, root / path)


def test_the_product_s_code_is_refused_and_says_what_the_stage_writes(workspace):
    said = _refusal(workspace, "notes-api/notes_api/storage.py")
    assert said and "`notes-api/notes_api/main.py`" in said and "Nothing was written." in said
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", said, re.I)


@pytest.mark.parametrize("path", ["notes-api/notes_api/main.py", "notes-api/start.sh", "notes-api/requirements.txt",
                                  "notes-api/tests/test_smoke.py", "notes-api/acceptance/test_scaffold_smoke.py",
                                  "notes-api/notes_api/__init__.py", "notes-api/stack-setup.json"])
def test_what_the_setup_is_asked_for_stays_open(workspace, path):
    assert _refusal(workspace, path) is None


def test_off_or_outside_the_setup_stage_nothing_is_refused(workspace, monkeypatch):
    monkeypatch.setenv("SETUP_SCOPE_GUARD", "off")
    assert _refusal(workspace, "notes-api/notes_api/storage.py") is None
    monkeypatch.setenv("SETUP_SCOPE_GUARD", "on")
    import app.observability.transcript as transcript

    monkeypatch.setattr(transcript, "_stage_from_config", lambda default="": "specialist_backend_0")
    assert _refusal(workspace, "notes-api/notes_api/storage.py") is None


def test_a_setup_with_no_layer_is_not_held(tmp_path, monkeypatch):
    import app.observability.transcript as transcript

    monkeypatch.setattr(transcript, "_stage_from_config", lambda default="": "stack_setup_0")
    monkeypatch.setenv("SETUP_SCOPE_GUARD", "on")
    record_the_setup_s_scope(tmp_path, "app", None)
    assert repository._beyond_the_setup_s_files(tmp_path, tmp_path / "app" / "server.py") is None
