"""The stages writing a Rust specification are told how its unit tests call the app, and that axum has no test client.

Measured on three Rust runs: the specification said the unit tests use "axum's TestClient", from the model's own
memory; the builders' guide says there is no `axum::test`, but the stages writing the specification never read it,
and every unit test it planned failed to compile.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import what_the_setup_decides
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_design_stages_hear_oneshot_and_that_there_is_no_test_client():
    lines = "\n".join(what_the_setup_decides(pack_named("rust-axum-api"), "notes-api", "notes_api"))

    assert "tower::ServiceExt::oneshot" in lines
    assert "no `axum::test` module and no `TestClient`" in lines
    assert not BANNED.search(lines)
