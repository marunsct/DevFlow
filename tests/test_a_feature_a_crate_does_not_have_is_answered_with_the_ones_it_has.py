"""A manifest asking a crate for a feature it does not have is answered with the features that version has.

Measured on four Rust runs: the manifest asked `rusqlite` for a `json` feature 0.37 does not have; cargo refused
("with features: `json` but `rusqlite` does not have these features"), the product never started, and fixers guessed
at the manifest for rounds with no list of the real features to read.
"""
from __future__ import annotations

import json
import re

from app.stacks import contract
from app.tools import package_registry

CARGO_SAID = """error: failed to select a version for `rusqlite`.
    ... required by package `notes_api v0.1.0 (/workspace/notes-api)`
versions that meet the requirements `^0.37` are: 0.37.0

the package `notes_api` depends on `rusqlite`, with features: `json` but `rusqlite` does not have these features.
"""

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _crates_io(url):
    assert url.endswith("/crates/rusqlite/0.37.0"), url
    return 200, json.dumps({"version": {"features": {"default": [], "bundled": [], "serde_json": [], "functions": []}}}).encode()


def test_the_install_note_names_the_features_the_version_has(monkeypatch):
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "_fetch", _crates_io)
    monkeypatch.setattr(package_registry, "_CACHE", {})

    said = contract._the_versions_that_exist(CARGO_SAID)

    assert "`rusqlite` 0.37.0 has no feature `json`" in said
    assert "`bundled`, `functions`, `serde_json`" in said and "`default`" not in said
    assert not BANNED.search(said)


def test_an_unreadable_registry_adds_nothing(monkeypatch):
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "_fetch", lambda url: (503, b""))
    monkeypatch.setattr(package_registry, "_CACHE", {})

    assert "has no feature" not in contract._the_versions_that_exist(CARGO_SAID)
