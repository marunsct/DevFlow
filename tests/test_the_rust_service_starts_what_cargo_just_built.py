"""The Rust service's kept start runs the binary cargo has just built, whatever its manifest calls the package.

Measured on a Rust axum run: a draft of `Cargo.toml` renamed the package `notes_api` to `notes-api`. Cargo then built
`target/debug/notes-api`, while the kept `start.sh` ran `./target/debug/notes_api`, a binary an earlier build had left:
for the last sprint attempt and the hidden tests every request was answered by code the sources no longer held (its
`execute("PRAGMA journal_mode=WAL")` long since fixed), and all nine hidden tests failed. In the pack's sandbox image,
the old start ran the old binary after the rename; `cargo build && exec cargo run --quiet` ran the new one, in the
start script's own process.
"""
from __future__ import annotations

from app.stacks import pack_named


def _the_start_script() -> str:
    pack = pack_named("rust-axum-api")
    return pack.filled_files(pack.files, "notes-api", "Notes", "notes_api")["start.sh"]


def test_the_start_names_no_binary_by_the_package_s_name():
    script = _the_start_script()

    assert "notes_api" not in script and "notes-api" not in script
    assert "target/" not in script


def test_the_start_still_builds_and_hands_its_process_to_the_service():
    script = _the_start_script()

    assert "cargo build &&" in script
    assert "exec cargo run" in script
