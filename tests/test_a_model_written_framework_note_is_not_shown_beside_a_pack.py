"""Beside a stack pack, the framework notes a model wrote for itself are not shown: the pack's guide is what is known.

Measured on a failed run of a compiled stack: the generated note said the framework ships a test client module, the
pack's guide in the same request said it does not, and the specification had followed the note.
"""
from __future__ import annotations

from app.plugins import middleware
from app.plugins.seed import SETUP
from app.server import plugin_store
from app.stacks import contract, pack_named


class _Store:
    def get_generated_framework_names(self):
        return {"axum"}


def _scaffolded(tmp_path):
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes", None, scaffolded=True)
    return str(tmp_path)


def test_a_generated_note_is_left_out_of_a_scaffolded_project(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_store.PluginStore, "shared", classmethod(lambda cls: _Store()))

    assert middleware._with_the_setup_notes(["rust", "Axum"], _scaffolded(tmp_path)) == ["rust"]


class _StoreOfTwo:
    def get_generated_framework_names(self):
        return {"axum", "a-framework-no-pack-names"}


def test_before_the_scaffold_a_framework_some_pack_covers_loses_its_generated_note(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_store.PluginStore, "shared", classmethod(lambda cls: _StoreOfTwo()))

    assert middleware._with_the_setup_notes(["rust", "axum"], str(tmp_path)) == ["rust", "rust" + SETUP]


def test_a_framework_no_pack_names_keeps_the_generated_note_it_has(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_store.PluginStore, "shared", classmethod(lambda cls: _StoreOfTwo()))
    name = "a-framework-no-pack-names"

    assert middleware._with_the_setup_notes([name], str(tmp_path)) == [name, name + SETUP]


def test_a_store_that_cannot_answer_leaves_the_notes(tmp_path, monkeypatch):
    def broken(cls):
        raise RuntimeError("no database")

    monkeypatch.setattr(plugin_store.PluginStore, "shared", classmethod(broken))

    assert middleware._with_the_setup_notes(["rust", "axum"], _scaffolded(tmp_path)) == ["rust", "axum"]
