"""Every Rust pack has cargo choose the crate releases its toolchain builds, and keeps that setting.

Measured on a Rust run: the sandbox's rustc 1.85 met `icu_collections 2.4` (it needs rustc 1.88), pulled in through
`url` by sqlx; the product never built whatever its code said, and the fixer pinned crates by hand round after round.
In the sandbox image, the same manifest with `incompatible-rust-versions = "fallback"` resolved `icu_collections 2.1.1`
and built.
"""
from __future__ import annotations

import re
import tomllib

import pytest

from app.stacks import packs
from app.stacks.packs.rust_axum_api import AXUM_KNOWN_ERRORS

RUST_PACKS = [p for p in (getattr(packs, n) for n in dir(packs)) if getattr(p, "language", None) == "rust"]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_there_are_rust_packs_to_check():
    assert {p.name for p in RUST_PACKS} >= {"rust-axum-api", "rust-cli", "rust-library"}


@pytest.mark.parametrize("pack", RUST_PACKS, ids=lambda p: p.name)
def test_cargo_is_told_to_fall_back_to_releases_the_toolchain_builds(pack):
    config = tomllib.loads(pack.files[".cargo/config.toml"])

    assert config["resolver"]["incompatible-rust-versions"] == "fallback"
    assert ".cargo/config.toml" in pack.kept_files


def test_a_crate_that_needs_a_newer_rust_is_answered_with_letting_cargo_choose_again():
    said = next(text for phrase, text in AXUM_KNOWN_ERRORS.items() if "is not supported by the following packages" in phrase)

    assert "Cargo.lock" in said and ".cargo/config.toml" in said
    assert not BANNED.search(said)


def test_sqlx_s_compile_time_query_macros_are_answered_and_kept_out_of_the_design():
    """Measured on the same run, once its crates resolved: `sqlx::query!` needed a live database at build time."""
    from app.stacks.packs.rust_axum_api import PACK

    said = next(text for phrase, text in AXUM_KNOWN_ERRORS.items() if "to use query macros online" in phrase)
    assert "sqlx::query(" in said and ".bind(" in said
    fact = next(f for f in PACK.design_facts if "query!" in f)
    assert "never" in fact
    assert not BANNED.search(said + fact)


@pytest.mark.parametrize("phrase, answer", [
    ("could not find `SqlitePoolOptions` in `sqlx`", "sqlx::sqlite::"),
    ("could not find `JournalMode` in `sqlite`", "SqliteJournalMode"),
    ("as it is not declared as mutable", "let mut"),
])
def test_the_one_line_faults_that_cost_a_round_each_are_answered(phrase, answer):
    """Measured on one Rust run: once its queries built, three one-line faults came one a round until its attempts ran
    out."""
    said = next(text for known, text in AXUM_KNOWN_ERRORS.items() if phrase in known)

    assert answer in said and not BANNED.search(said)
