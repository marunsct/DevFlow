"""A credential file is refused with where the setting belongs (measured live).

A fixer whose product failed to start for want of a value wrote a file named for
credentials, five times. Nothing that starts the product reads such a file, and
the refusal only named the pattern, so the call was repeated. It now says the
file would change nothing and where the value goes.
"""
from __future__ import annotations

import re

import pytest

from app.tools import repository

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_write_to_a_credential_file_says_where_the_setting_goes(tmp_path):
    with pytest.raises(repository.RepositoryToolError) as refused:
        repository.write_approved_artifact(tmp_path, "app/.env", "KEY=value\n")

    text = str(refused.value)
    assert "credential file pattern" in text
    assert "settings code" in text
    assert "PORT" in text and "DATA_DIR" in text
    assert not BANNED.search(text)


def test_an_edit_of_a_credential_file_says_the_same(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("KEY=1\n")

    with pytest.raises(repository.RepositoryToolError) as refused:
        repository.edit_approved_artifact(tmp_path, "app/.env", "KEY=1", "KEY=2")

    assert "settings code" in str(refused.value)
