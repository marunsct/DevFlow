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
], ids=["body-extractor-first", "router-without-its-state", "app-returns-a-router-still-waiting", "no-axum-test"])
def test_the_error_is_given_its_cause(tmp_path, error, cause):
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [_defect(error)])

    assert KNOWN_CAUSE in defect.actual_behavior and cause in defect.actual_behavior
    assert not BANNED.search(defect.actual_behavior)
