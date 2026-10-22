"""A fixer that names a locked test by its name, not its file, is read as blaming the suite.

Measured on a gate run: a fixer changed nothing and reported
"test_ac7_persistence_after_restart has an unfixable typo" - a locked test
signing in as the wrong account - and no dispute was held, because only the
suite's file names were looked for.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import workflow


def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setattr(suite, "suite_files", lambda root: [Path("acceptance/test_persistence.py")])
    monkeypatch.setattr(suite, "declared_tests", lambda root: [
        ("acceptance/test_persistence.py", "test_ac7_persistence_after_restart"),
        ("acceptance/test_items.py", "test_ac3_creates[empty]"),
    ])
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


def test_a_test_s_own_name_is_blame(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch)
    assert workflow._blames_a_locked_test(state, ["test_ac7_persistence_after_restart has an unfixable typo on line 54"])
    assert workflow._blames_a_locked_test(state, ["test_ac3_creates[empty] expects a field no criterion names"])
    assert workflow._blames_a_locked_test(state, ["acceptance/test_persistence.py is wrong"])


def test_a_product_file_or_a_longer_name_is_not(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch)
    assert not workflow._blames_a_locked_test(state, ["tasks_api/app.py raises on restart"])
    assert not workflow._blames_a_locked_test(state, ["test_ac7_persistence_after_restart_twice fails"])
