"""A Rust service's builders are told the imports a unit test really uses, and that `app()` returns a plain `Router`.

Measured on one Rust run: its unit tests imported `axum::test`, which does not exist, through two fix rounds, and
`app()` returned a `Router<AppState>` that `axum::serve` would not serve. The guide named `oneshot` and neither.
"""
from __future__ import annotations

import re

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
