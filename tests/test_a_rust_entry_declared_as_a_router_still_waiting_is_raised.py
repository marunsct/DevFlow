"""The Rust entry's declaration is held to `pub fn app() -> Router` at every round, wherever its errors are reported.

Measured on five Rust runs: `app()` was declared `-> Router<AppState>` (once `-> Router<Extension<AppState>>`), which
`axum::serve` cannot serve; the compiler reported it in `main.rs`, and fixers edited `main.rs` attempt after attempt.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import acceptance_nodes
from app.stacks import contract, entry_exports, pack_named


def _a_rust_project(tmp_path, monkeypatch, entry):
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "on")
    pack = pack_named("rust-axum-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", None, scaffolded=True)
    for relative, text in pack.render("notes-api", "Notes", None).items():
        (tmp_path / "notes-api" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes-api" / relative).write_text(text)
    if entry is not None:
        (tmp_path / "notes-api" / "src" / "lib.rs").write_text(entry)
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


@pytest.mark.parametrize("entry, raised", [
    (None, False),  # the scaffold's own
    ("pub fn app() -> Router<AppState> {\n    Router::new().with_state(AppState::default())\n}\n", True),
    ("pub fn app() -> Router<Extension<AppState>> {\n    Router::new()\n}\n", True),
    ("pub fn app() -> Router {\n    let state = AppState::load();\n    Router::new().with_state(state)\n}\n", False),
], ids=["the-scaffold", "router-waiting-for-state", "router-with-an-extension", "plain-router"])
def test_a_changed_declaration_is_raised_against_its_own_file(tmp_path, monkeypatch, entry, raised):
    state = _a_rust_project(tmp_path, monkeypatch, entry)

    found = [d for d in acceptance_nodes.pack_contract_defects(state) if entry_exports.NO_LONGER_DECLARES in d.description]

    assert bool(found) is raised
    if raised:
        assert found[0].affected_files == ["notes-api/src/lib.rs"] and "`pub fn app() -> Router`" in found[0].description
        assert entry_exports.still_raised(str(tmp_path), found[0].description) is True
