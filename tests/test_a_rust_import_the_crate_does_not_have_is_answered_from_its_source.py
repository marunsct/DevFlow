"""A Rust import or path the compiler cannot resolve is answered with where the crate really declares the name.

Measured on Rust runs, one compile round each: `use axum::extract::JsonRejection` (it is in
`axum::extract::rejection`), `sqlx::SqlitePoolOptions` (it is in `sqlx::sqlite`) and `rusqlite::JournalMode` (there is
none). rustc names the path the code asked for, not where the name is, so each rewrite guessed again. Cargo unpacks
each crate's source under the workspace's `.agent-home` (the sandbox's HOME, CARGO_HOME unset), and the source says.
The crates below are small stand-ins laid out as cargo lays them out; the error lines are rustc's own wording.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.analysis import compiler_check, language_service

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")


def _crate(workspace: Path, unpacked: str, files: dict[str, str]) -> None:
    directory = workspace / ".agent-home" / ".cargo" / "registry" / "src" / "index.crates.io-0000" / unpacked
    for relative, text in {"Cargo.toml": f'[package]\nname = "{unpacked.rsplit("-", 1)[0]}"\n', **files}.items():
        (directory / relative).parent.mkdir(parents=True, exist_ok=True)
        (directory / relative).write_text(text)


def _registry(workspace: Path) -> None:
    _crate(workspace, "axum-0.8.9", {
        "src/lib.rs": "pub mod extract;\nmod json;\npub use self::json::Json;\n",
        "src/json.rs": "pub struct Json<T>(pub T);\n",
        "src/extract/mod.rs": (
            "pub mod rejection;\nmod state;\n"
            "pub use self::state::State;\npub use crate::Json;\n"
            "#[cfg(test)]\nmod tests {\n    pub fn JsonRejection() {}\n}\n"
        ),
        "src/extract/state.rs": "pub struct State<S>(pub S);\n",
        # As axum declares its rejections: inside a macro invocation's body, with braces in a comment and a string.
        "src/extract/rejection.rs": (
            "//! Rejection types: { not code }\n"
            "macro_rules! composite_rejection { ($($t:tt)*) => {} }\n"
            "composite_rejection! {\n"
            "    /// Rejection used for `Json`. Example: `{ pub struct Fake; }`\n"
            "    pub enum JsonRejection {\n        JsonDataError(JsonDataError),\n    }\n"
            "}\n"
            "pub struct JsonDataError;\n"
            "impl JsonDataError {\n    pub fn body_text(&self) -> String { \"{\".to_owned() }\n}\n"
        ),
    })
    _crate(workspace, "sqlx-0.8.6", {
        "src/lib.rs": "pub use sqlx_core::query;\npub use sqlx_sqlite::{\n    self as sqlite, Sqlite, SqlitePool,\n};\n",
    })
    _crate(workspace, "sqlx-core-0.8.6", {"src/lib.rs": "pub fn query() {}\n"})
    _crate(workspace, "sqlx-sqlite-0.8.6", {
        "src/lib.rs": (
            "mod options;\npub use options::{SqliteConnectOptions, SqliteJournalMode};\n"
            "pub struct Sqlite;\npub type SqlitePool = Pool<Sqlite>;\n"
            "pub type SqlitePoolOptions = crate::pool::PoolOptions<Sqlite>;\n"
        ),
        "src/options/mod.rs": "pub struct SqliteConnectOptions;\npub enum SqliteJournalMode { Wal }\n",
    })
    _crate(workspace, "rusqlite-0.32.1", {
        "src/lib.rs": "pub mod types;\npub struct Connection;\npub struct Transaction;\npub enum TransactionBehavior { Deferred }\n",
        "src/types/mod.rs": "pub enum Type { Null }\n",
    })


def _project(workspace: Path, source: str) -> Path:
    importer = workspace / "notes-api" / "src" / "main.rs"
    importer.parent.mkdir(parents=True)
    (workspace / "notes-api" / "Cargo.toml").write_text('[package]\nname = "notes-api"\n')
    importer.write_text(source)
    return importer


def _said(workspace: Path, importer: Path, message: str, line: int = 1) -> str:
    return language_service.the_names_the_module_has(workspace / "notes-api", importer,
                                                     {"message": message, "line": line})


def test_a_name_in_a_submodule_is_named_by_its_path_from_the_crate_root(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "use axum::extract::JsonRejection;\n")

    said = _said(tmp_path, importer, "unresolved import `axum::extract::JsonRejection`: no `JsonRejection` in `extract`")

    assert "`axum::extract::rejection::JsonRejection`" in said
    assert "0.8.9" in said


def test_a_name_a_module_re_exports_through_pub_use_is_named_where_it_is_re_exported(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "use axum::State;\n")

    said = _said(tmp_path, importer, "unresolved import `axum::State`: no `State` in the root")

    assert "`axum::extract::State`" in said
    assert "extract::state::State" not in said


def test_a_module_another_crate_gives_under_an_alias_is_followed(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "fn main() {\n    let pool = sqlx::SqlitePoolOptions::new();\n}\n")

    said = _said(tmp_path, importer, "failed to resolve: could not find `SqlitePoolOptions` in `sqlx`", line=2)

    assert "`sqlx::sqlite::SqlitePoolOptions`" in said


def test_a_name_the_crate_does_not_have_comes_back_with_the_nearest_names_it_has(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "fn open() {\n    let mode = sqlx::sqlite::JournalMode::Wal;\n}\n")

    said = _said(tmp_path, importer, "failed to resolve: could not find `JournalMode` in `sqlite`", line=2)

    assert "no public `JournalMode`" in said
    assert "`SqliteJournalMode`" in said


def test_a_crate_with_no_such_name_and_none_near_it_says_so(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "fn open() {\n    let mode = rusqlite::JournalMode::Wal;\n}\n")

    said = _said(tmp_path, importer, "failed to resolve: could not find `JournalMode` in `rusqlite`", line=2)

    assert "`rusqlite` 0.32.1's source has no public `JournalMode`" in said
    assert not BANNED.search(said)


def test_a_private_module_s_items_and_a_method_are_not_offered_as_paths(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "use axum::extract::body_text;\n")

    said = _said(tmp_path, importer, "unresolved import `axum::extract::body_text`: no `body_text` in `extract`")

    assert "no public `body_text`" in said


def test_a_module_declared_pub_under_one_feature_and_private_under_another_is_public(tmp_path):
    """As tokio declares its modules: `cfg_sync! { pub mod sync; }` then `cfg_not_sync! { mod sync; }`."""
    _registry(tmp_path)
    _crate(tmp_path, "tokio-1.48.0", {
        "src/lib.rs": "cfg_sync! {\n    pub mod sync;\n}\ncfg_not_sync! {\n    mod sync;\n}\n",
        "src/sync/mod.rs": "cfg_sync! {\n    mod mutex;\n    pub use mutex::{Mutex, MutexGuard};\n}\n",
        "src/sync/mutex.rs": "pub struct Mutex<T>(T);\npub struct MutexGuard;\n",
    })
    importer = _project(tmp_path, "use tokio::Mutex;\n")

    said = _said(tmp_path, importer, "unresolved import `tokio::Mutex`: no `Mutex` in the root")

    assert "`tokio::sync::Mutex`" in said


def test_a_crate_cargo_has_not_unpacked_or_the_project_s_own_module_says_nothing(tmp_path):
    _registry(tmp_path)
    importer = _project(tmp_path, "use tokio::sync::Mutexx;\nuse crate::store::Store;\n")

    assert _said(tmp_path, importer, "unresolved import `tokio::sync::Mutexx`: no `Mutexx` in `sync`") == ""
    assert _said(tmp_path, importer, "unresolved import `crate::store::Store`: no `Store` in `store`", line=2) == ""


def test_an_importer_in_another_language_is_not_read_as_rust(tmp_path):
    _registry(tmp_path)
    importer = tmp_path / "goapp" / "main.go"
    importer.parent.mkdir()
    importer.write_text('package main\nimport "axum/extract"\n')

    said = language_service.the_names_the_module_has(
        tmp_path / "goapp", importer, {"message": "unresolved import `axum::extract::JsonRejection`", "line": 2})

    assert said == ""


# --- where it is given -------------------------------------------------------------------------------------

_JSON_REJECTION = {"file": "notes-api/src/main.rs", "line": 1, "code": "error[E0432]",
                   "message": "unresolved import `axum::extract::JsonRejection`: no `JsonRejection` in `extract`"}


def test_the_stage_that_wrote_the_import_is_told_where_the_name_is(tmp_path, monkeypatch):
    from app.graph import workflow

    _registry(tmp_path)
    _project(tmp_path, "use axum::extract::JsonRejection;\n")
    monkeypatch.setattr(compiler_check, "findings", lambda root, project, files: [dict(_JSON_REJECTION)])

    told = workflow._what_the_compiler_says_of(str(tmp_path), {"notes-api/src/main.rs"}, "defect_fix_1_0", "notes-api")

    assert len(told) == 1
    assert told[0].startswith("- In `notes-api/src/main.rs` line 1: unresolved import `axum::extract::JsonRejection`")
    assert "`axum::extract::rejection::JsonRejection`" in told[0]


def test_the_sprint_gate_s_defect_names_where_the_name_is(tmp_path, monkeypatch):
    from app.graph import engineering

    _registry(tmp_path)
    _project(tmp_path, "use axum::extract::JsonRejection;\n")
    monkeypatch.setattr(engineering.ci, "changed_since", lambda root, since: ["notes-api/src/main.rs"])
    monkeypatch.setattr(compiler_check, "findings", lambda *a, **k: [dict(_JSON_REJECTION)])
    monkeypatch.setattr(engineering, "_owner_of", lambda state, work_order: "backend")

    defects = engineering._what_the_compiler_says({}, str(tmp_path), "abc", "notes-api")

    assert len(defects) == 1
    assert "`axum::extract::rejection::JsonRejection`" in defects[0].expected_behavior
    assert not BANNED.search(defects[0].expected_behavior)
