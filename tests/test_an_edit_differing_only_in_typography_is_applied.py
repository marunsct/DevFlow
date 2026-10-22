"""An edit whose passage differs from the file only in quotes, dashes or non-breaking spaces is applied (Initiative G, Unicode half).

Measured across 280 "could not find that text" misses: 4 differed only in a
curly quote, a long dash or a non-breaking space - a model types the plain
character, or the file holds the plain one and the model the typographic.
"""
from __future__ import annotations

import pytest

from app.tools import repository


def test_a_box_drawn_comment_written_with_hyphens_is_found(tmp_path):
    (tmp_path / "app.js").write_text("// \u2500\u2500 errors \u2500\u2500\nconst x = 1;\n")

    result = repository.edit_approved_artifact(tmp_path, "app.js", "// -- errors --\nconst x = 1;", "// -- errors --\nconst x = 2;")

    assert "const x = 2;" in (tmp_path / "app.js").read_text()
    assert "quotes, dashes and non-breaking spaces" in str(result)


def test_curly_quotes_in_the_file_match_straight_ones_sent(tmp_path):
    (tmp_path / "README.md").write_text("Say \u201chello\u201d to it.\nNext line.\n")

    repository.edit_approved_artifact(tmp_path, "README.md", 'Say "hello" to it.', 'Say "hi" to it.')

    assert 'Say "hi" to it.' in (tmp_path / "README.md").read_text()


def test_two_plain_matches_are_refused_as_before(tmp_path):
    (tmp_path / "a.txt").write_text("it\u2019s one\nit's one\n")

    with pytest.raises(repository.RepositoryToolError):
        repository.edit_approved_artifact(tmp_path, "a.txt", "it\u2018s one", "x")


def test_an_ordinary_miss_is_still_a_miss(tmp_path):
    (tmp_path / "a.txt").write_text("alpha\n")

    with pytest.raises(repository.RepositoryToolError):
        repository.edit_approved_artifact(tmp_path, "a.txt", "beta", "gamma")
