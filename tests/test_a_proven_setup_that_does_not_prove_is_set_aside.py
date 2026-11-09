"""A proven setup whose replay does not prove is set aside, not replayed on every run of its stack.

Measured on one night: one entry's install ran a bare `pip` with no project environment; it failed its proof on three
runs in a row and cost each 15 to 25 minutes before the setup stage was asked.
"""
from __future__ import annotations

import json

from app.stacks import custom_setup


def _library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    entry = library / "language-python-framework-fastapi.json"
    entry.write_text(json.dumps({"declaration": "{}", "files": {"app.py": "x = 1\n"}}))
    monkeypatch.setattr(custom_setup, "_entry_for", lambda stack: entry)
    return library, entry


def test_the_replayed_entry_is_moved_aside_and_no_longer_found(tmp_path, monkeypatch):
    library, entry = _library(tmp_path, monkeypatch)
    project = tmp_path / "work" / "app"
    project.mkdir(parents=True)

    assert custom_setup.replay(project, stack=None)
    assert custom_setup.set_aside_what_did_not_prove(project) == entry.name

    assert not entry.exists() and (library / "failed" / entry.name).exists()
    assert list(library.glob("*.json")) == [], "the library's own listing no longer holds it"


def test_nothing_replayed_sets_nothing_aside(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    assert custom_setup.set_aside_what_did_not_prove(project) == ""
