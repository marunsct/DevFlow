"""A read that lands on a directory is a question about its contents.

One run's `specialist_backend_3` read `/simple-to-do-list-app/tests` four
times and was told four times that a directory of that name existed at that
path - which it had just typed. The answer it wanted, the list of files in
there, cost one `iterdir` on a call that had already failed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workspace_backend import MAX_DIRECTORY_ENTRIES, _Suggesting


@pytest.fixture()
def backend(tmp_path: Path):
    (tmp_path / "proj" / "tests").mkdir(parents=True)
    (tmp_path / "proj" / "tests" / "a.test.mjs").write_text("x")
    (tmp_path / "proj" / "tests" / "helpers").mkdir()
    (tmp_path / "proj" / "empty").mkdir()
    (tmp_path / "proj" / "app.js").write_text("y")

    class Backend(_Suggesting):
        cwd = str(tmp_path)

    return Backend()


def test_a_directory_read_is_answered_with_its_contents(backend) -> None:
    hint = backend._what_is_in_it("/proj/tests")

    assert "is a directory, not a file" in hint
    assert "a.test.mjs" in hint
    assert "helpers/" in hint, "a subdirectory is marked as one"


def test_an_empty_directory_says_it_is_empty(backend) -> None:
    """Otherwise "it contains: " trails off and reads like a truncation."""
    assert "it is empty" in backend._what_is_in_it("/proj/empty")


def test_a_file_is_not_a_directory(backend) -> None:
    assert backend._what_is_in_it("/proj/app.js") == ""


def test_a_path_that_does_not_exist_gets_nothing_here(backend) -> None:
    """That case belongs to `_where_it_actually_is`, which searches for it."""
    assert backend._what_is_in_it("/nowhere") == ""


def test_a_huge_directory_is_summarised(tmp_path: Path) -> None:
    big = tmp_path / "node_heavy"
    big.mkdir()
    for index in range(MAX_DIRECTORY_ENTRIES + 12):
        (big / f"file{index:03d}.js").write_text("x")

    class Backend(_Suggesting):
        cwd = str(tmp_path)

    hint = Backend()._what_is_in_it("/node_heavy")

    assert "and 12 more" in hint
