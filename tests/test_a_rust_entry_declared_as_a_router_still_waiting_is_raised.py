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


def test_the_callers_that_pass_arguments_are_named_with_the_declaration(tmp_path, monkeypatch):
    """Measured on one run: `app` took the store, `main.rs` called `app(Arc::new(store))`, and the defect named only
    `lib.rs`. Each fix restored `pub fn app() -> Router` there alone, `main.rs` no longer compiled, the product did not
    start, and three fixes were reverted for it."""
    state = _a_rust_project(tmp_path, monkeypatch,
                            "pub fn app(store: Arc<dyn Store>) -> Router {\n    Router::new().with_state(store)\n}\n")
    main = tmp_path / "notes-api" / "src" / "main.rs"
    main.write_text("use notes_api::app;\n// app(x) in a comment is not a call\n"
                    "async fn main() {\n    axum::serve(listener, app(Arc::new(store))).await.unwrap();\n}\n")

    found = [d for d in acceptance_nodes.pack_contract_defects(state) if entry_exports.NO_LONGER_DECLARES in d.description]

    assert found[0].affected_files == ["notes-api/src/lib.rs", "notes-api/src/main.rs"]
    assert "app(Arc::new(store))" in found[0].expected_behavior
    assert entry_exports.still_raised(str(tmp_path), found[0].description) is True


def test_a_caller_using_the_declaration_as_it_is_is_not_named(tmp_path, monkeypatch):
    state = _a_rust_project(tmp_path, monkeypatch, "pub fn app(store: Store) -> Router {\n    Router::new()\n}\n")

    found = [d for d in acceptance_nodes.pack_contract_defects(state) if entry_exports.NO_LONGER_DECLARES in d.description]

    assert found[0].affected_files == ["notes-api/src/lib.rs"]
