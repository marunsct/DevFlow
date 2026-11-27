"""A Rust service's builders are told the imports a unit test really uses, and that `app()` returns a plain `Router`.

Measured on one Rust run: its unit tests imported `axum::test`, which does not exist, through two fix rounds, and
`app()` returned a `Router<AppState>` that `axum::serve` would not serve. The guide named `oneshot` and neither.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import what_the_setup_decides
from app.graph import builder_facts
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _guide() -> str:
    return " ".join(pack_named("rust-axum-api").guide.split())


def test_the_guide_says_there_is_no_axum_test_and_names_the_imports():
    guide = _guide()
    assert "There is no `axum::test`" in guide
    for name in ("axum::body::Body", "axum::http::{Request, StatusCode}", "http_body_util::BodyExt", "tower::ServiceExt"):
        assert name in guide


def test_the_guide_says_app_applies_its_state_itself():
    assert "`app()` returns a plain `Router`" in _guide() and ".with_state(state)" in _guide()


def test_the_guide_reaches_the_builders_whole_and_uses_no_banned_word():
    guide = pack_named("rust-axum-api").guide
    assert len(guide) <= builder_facts.MOST_GUIDE_CHARACTERS
    assert not BANNED.search(guide)


def test_a_rust_builder_is_told_axum_0_8_s_extractor_body_limit_and_path_forms():
    """Measured on a Rust run on axum 0.8.9: the drafts wrote a custom extractor under `#[async_trait]` (axum 0.7's
    form, E0195 on 0.8), a body limit through a `tower::Limit` that does not exist, a route helper declared `-> Router`
    that `app()` then gave its state, and a `/notes/:id` route, which 0.8 refuses when it builds the router."""
    guide = _guide()
    assert "plain `async fn from_request_parts(parts: &mut Parts, state: &S)`" in guide
    assert "never under `#[async_trait]`" in guide and "needs no `async-trait` crate" in guide
    assert "`.layer(axum::extract::DefaultBodyLimit::max(bytes))`" in guide and "tower has no `Limit`" in guide
    assert "`/items/{id}`" in guide and "refuses `/:id`" in guide
    assert "A helper that builds routes for `app()` to give the state to is declared `-> Router<AppState>`" in guide


def test_the_rust_specification_is_told_axum_0_8_s_body_limit_and_extractor_forms():
    """Measured on the same run: the specification named "a body size limit via tower::Limit"."""
    said = " ".join(what_the_setup_decides(pack_named("rust-axum-api"), "notes-api", "notes_api"))
    assert "`.layer(axum::extract::DefaultBodyLimit::max(bytes))`" in said and "tower has no `Limit`" in said
    assert "never under `#[async_trait]`" in said
    assert not BANNED.search(said)


def test_a_rust_builder_is_told_the_signature_keeps_the_router_waiting():
    """Measured: `app()` ended in `.with_state(state)` but was declared `-> Router<AppState>`."""
    assert "declared `-> Router<AppState>`, it still waits for its state after `.with_state`" in _guide()
