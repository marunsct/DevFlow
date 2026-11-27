"""An axum service's two known compiler errors reach the fixer with their cause.

Measured on two Rust runs: a handler taking `Json` before `State` failed as "`Handler<_, _>` is not satisfied" for three
fix rounds, and `axum::serve` given a `Router<AppState>` failed every round of a run.
"""
from __future__ import annotations

import re

import pytest

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _defect(text):
    return ReportedDefect(description=f"notes-api/src/lib.rs line 16: {text}", severity="major",
                          reproduction_steps="cargo build", expected_behavior="it builds", actual_behavior=text,
                          affected_files=["notes-api/src/lib.rs"], owner="backend")


@pytest.mark.parametrize("error, cause", [
    ("the trait bound `fn(Json<CreateNote>, State<AppState>) -> Response {create_note}: Handler<_, _>` is not satisfied",
     "must be its last argument"),
    ("the trait bound `for<'a> Router<AppState>: tower_service::Service<IncomingStream<'a, TcpListener>>` is not satisfied",
     "`.with_state(state)`"),
    ("mismatched types: expected `Router`, found `Router<AppState>`", "build the state inside `app()`"),
    ("error[E0433]: failed to resolve: could not find `test` in `axum`", "`tower::ServiceExt::oneshot`"),
    ("error[E0599]: the method `oneshot` exists for struct `Router<AppState>`, but its trait bounds were not satisfied",
     "build the state inside `app()`"),
    ("error[E0382]: use of moved value: `app`: value used here after move", "`oneshot` takes the router by value"),
    ("unresolved import `crate::models`: could not find `models` in the crate root", "`pub mod <name>;`"),
    ("module `models` is private: private module", "`pub mod <name>;`, not `mod <name>;`"),
    ("failed to resolve: could not find `JournalMode` in `rusqlite`: could not find `JournalMode`",
     "`conn.pragma_update(None, \"journal_mode\", \"WAL\")?`"),
    ("error[E0603]: struct import `AppState` is private", "re-export it there with `pub use`"),
    ("cannot borrow `*conn` as mutable, as it is behind a `&` reference: `conn` is a `&` reference",
     "`conn.unchecked_transaction()?`"),
    ("`?` couldn't convert the error to `rusqlite::Error`: the trait `From<std::io::Error>` is not implemented",
     "`Result<T, Box<dyn std::error::Error + Send + Sync>>`"),
    ("answered 500: Missing request extension: Extension of type `AppState` was not found", "`State(state): State<AppState>`"),
    ("The default runtime flavor is `multi_thread`, but the `rt-multi-thread` feature is disabled", "\"rt-multi-thread\", \"net\"]"),
], ids=["body-extractor-first", "router-without-its-state", "app-returns-a-router-still-waiting", "no-axum-test",
        "a-test-given-a-router-still-waiting", "a-router-sent-two-requests", "a-module-not-declared",
        "a-private-module", "no-journal-mode-type", "a-struct-only-imported", "a-mutable-call-through-a-shared-reference", "an-error-question-mark-cannot-convert", "tokio-without-its-runtime", "extension-and-state-mixed"])
def test_the_error_is_given_its_cause(tmp_path, error, cause):
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect(error)])

    assert KNOWN_CAUSE in defect.actual_behavior and cause in defect.actual_behavior
    assert not BANNED.search(defect.actual_behavior)


@pytest.mark.parametrize("error, cause", [
    # The compiler's words as the harness's build check reported them on axum 0.8.9, rustc 1.85.
    ("lifetime parameters or bounds on associated function `from_request_parts` do not match the trait declaration: "
     "lifetimes do not match associated function in trait", "delete that attribute line above the `impl`"),
    ("lifetime parameters or bounds on method `from_request` do not match the trait declaration",
     "delete that attribute line above the `impl`"),
    ("mismatched types: expected `()`, found `AppState`", "`pub fn routes() -> Router<AppState>`"),
    ("unresolved import `tower::Limit`: no `Limit` in the root", "`.layer(axum::extract::DefaultBodyLimit::max(<bytes>))`"),
    ("failed to resolve: could not find `limit` in `tower`", "`.layer(axum::extract::DefaultBodyLimit::max(<bytes>))`"),
], ids=["an-extractor-under-async-trait", "a-body-extractor-under-async-trait", "state-given-to-a-router-of-unit",
        "no-tower-limit", "tower-limit-behind-its-feature"])
def test_an_axum_0_8_error_is_given_its_version_true_cause(tmp_path, error, cause):
    """Measured on a Rust run on axum 0.8.9: an extractor written `#[async_trait::async_trait] impl FromRequestParts`
    (axum 0.7's form) failed with E0195 at three building stages and a fixer, and none removed the attribute; a helper
    declared `-> Router` was given `.with_state(state)`; two fixes imported a `tower::Limit` that does not exist."""
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect(error)])

    assert KNOWN_CAUSE in defect.actual_behavior and cause in defect.actual_behavior
    assert not BANNED.search(defect.actual_behavior)


def test_the_extractor_s_cause_says_axum_0_7_wanted_the_attribute(tmp_path):
    """The same E0195 has the opposite cause on axum 0.7, whose trait is `#[async_trait]`: the version decides."""
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect(
        "lifetime parameters or bounds on associated function `from_request_parts` do not match the trait declaration")])

    assert "read axum's version in `Cargo.toml`" in defect.actual_behavior
    assert "up to axum 0.7 is the trait `#[async_trait]`" in defect.actual_behavior


def test_one_line_carrying_two_phrases_of_an_error_is_given_its_cause_once(tmp_path):
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect("unresolved import `tower::limit`: could not find `limit` in `tower`")])

    assert defect.actual_behavior.count(KNOWN_CAUSE) == 1


def test_a_router_error_names_the_return_type_that_keeps_it_waiting(tmp_path):
    """Measured: `app()` ended in `.with_state(state)` but was declared `-> Router<AppState>`; told to apply the state,
    the fixer found it applied and left the error open."""
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect(
        "the trait bound `for<'a> Router<AppState>: tower_service::Service<IncomingStream<'a, TcpListener>>` is not "
        "satisfied")])

    assert "`fn app() -> Router<AppState>` still waits for its state after `.with_state`" in defect.actual_behavior
    # Measured: the error was reported in `main.rs`, and fixers kept editing it; the signature is in `src/lib.rs`.
    assert "change the signature in `src/lib.rs` to `pub fn app() -> Router`" in defect.actual_behavior
    assert not BANNED.search(defect.actual_behavior)
