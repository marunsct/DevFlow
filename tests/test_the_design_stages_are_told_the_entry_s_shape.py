"""The stages that write and judge the specification are told the shape a pack's entry must keep.

Measured on one Rust run: the specification gave `pub fn build_router() -> Router<AppState>`, which `axum::serve`
cannot serve. Two sprint attempts built to it and the technical lead re-planned to it - adding a dependency that could
not help - while every builder's guide said a plain `Router`. Only the builders had the pack's guide.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import what_the_setup_decides
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_rust_specification_is_told_app_returns_a_plain_router():
    said = " ".join(what_the_setup_decides(pack_named("rust-axum-api"), "notes-api", "notes_api"))
    assert "`pub fn app() -> Router`" in said
    assert "never `Router<AppState>`" in said and ".with_state(state)" in said
    assert not BANNED.search(said)


def test_a_pack_with_no_design_facts_is_told_nothing_more():
    assert not any("never `Router<AppState>`" in line
                   for line in what_the_setup_decides(pack_named("go-http-api"), "notes-api", "notes-api"))
