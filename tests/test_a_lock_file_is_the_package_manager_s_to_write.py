"""A lock file is the package manager's: a model's write is refused, and one an install refuses is written again.

Measured on a Rust run: a re-planned work order said to regenerate `Cargo.lock`, a model wrote one by hand with
invented checksums (`7360491ce676a36e5c5c5c...`), and every install after it was refused ("unable to verify that
`fallible-streaming-iterator` is the same as when the lockfile was generated") - the product never started.
"""
from __future__ import annotations

import re

import pytest

from app.stacks import contract, pack_named
from app.tools.repository import RepositoryToolError, write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["Cargo.lock", "package-lock.json", "go.sum", "composer.lock"])
def test_a_lock_file_written_by_hand_is_refused(tmp_path, name):
    (tmp_path / "app").mkdir()

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, f"app/{name}", "checksum = \"7360491ce676a36e5c5c5c5c\"\n")

    assert not (tmp_path / "app" / name).exists()
    assert "package manager" in str(refused.value) and not BANNED.search(str(refused.value))


def test_an_install_refused_on_a_lock_file_checksum_removes_it_and_installs_once_more(tmp_path):
    pack = pack_named("rust-axum-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", "notes_api", scaffolded=True)
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    (tmp_path / "notes-api" / "Cargo.toml").write_text('[package]\nname = "notes_api"\n')
    (tmp_path / "notes-api" / "Cargo.lock").write_text('checksum = "7360491ce676a36e5c5c5c5c"\n')
    calls = []

    def runner(argv, category, project):
        calls.append(list(argv))
        if (tmp_path / "notes-api" / "Cargo.lock").exists():
            return {"returncode": "101", "network": "bridge", "stderr":
                    "error: checksum for `fallible-streaming-iterator v0.1.9` changed between lock files\n"
                    "unable to verify that `fallible-streaming-iterator v0.1.9` is the same as when the lockfile was generated"}
        return {"returncode": "0", "network": "bridge", "stdout": "", "stderr": ""}

    notes = contract.install_if_the_manifests_changed(tmp_path, runner=runner)

    assert not (tmp_path / "notes-api" / "Cargo.lock").exists()
    assert len(calls) >= 2 and calls[0] == calls[1]
    assert not any(contract.INSTALL_FAILED in note for note in notes)
