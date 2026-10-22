"""A database file is refused as a database, with the cause a leftover one points at.

Measured live: a fixer whose suite failed with `UNIQUE constraint failed:
users.username` tried to delete the project's `data/task_management.db` and was
told it "looks like credential material". It spent its next calls listing the
data directory and running a script to find the file. The suite starts the
product with a fresh `DATA_DIR`; the product's database URL was a file in the
working directory, outside it. That is what the refusal now says.
"""

from __future__ import annotations

import re

import pytest

from app.tools.repository import RepositoryToolError, delete_approved_artifact, move_approved_artifact

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _project(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "app.db").write_bytes(b"SQLite format 3\x00")
    (tmp_path / ".env").write_text("SECRET=x\n")
    return tmp_path


def _refused(call) -> str:
    with pytest.raises(RepositoryToolError) as refused:
        call()
    return str(refused.value)


def test_deleting_a_database_names_data_dir_not_credentials(tmp_path):
    root = _project(tmp_path)

    said = _refused(lambda: delete_approved_artifact(root, "data/app.db"))

    assert "credential" not in said
    assert "database file" in said and "`DATA_DIR`" in said
    assert (root / "data" / "app.db").exists()


def test_moving_a_database_is_refused_the_same_way(tmp_path):
    root = _project(tmp_path)

    said = _refused(lambda: move_approved_artifact(root, "data/app.db", "data/old.db"))

    assert "database file" in said and "`DATA_DIR`" in said


def test_a_credential_file_is_still_refused_as_one(tmp_path):
    root = _project(tmp_path)

    assert "credential material" in _refused(lambda: delete_approved_artifact(root, ".env"))


def test_the_refusal_holds_for_any_product(tmp_path):
    said = _refused(lambda: delete_approved_artifact(_project(tmp_path), "data/app.db"))

    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", said, re.I), word
