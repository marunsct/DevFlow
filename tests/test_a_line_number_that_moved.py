""""Read the file again" costs a call to rediscover what the tool already has.

`replace_lines` refuses when `expect_start` does not match the line asked
for, which is right - a stale line number silently changing the wrong place
is the damage the argument exists to prevent. What it then said was "Read the
file again and use the new line numbers", which costs a read of the whole
file and a second attempt.

Measured on run-ed05e20e: three of the run's ten costly failures were this
refusal, and in every one the expected line was two or three lines from where
the caller looked. `specialist_testing_2` asked for
`export function renderTaskList(...)` at line 195 twice, and it was at 197
both times.

This matters more now than it did: two `edit_artifact` refusals were just
rewritten to send the model to `replace_lines`, so a dead end here is a dead
end at the end of the path the harness recommends.

It reports rather than applies. `expect_start` pins only the FIRST line, so
shifting the whole range by the same offset would delete whatever now sits at
the other end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    read_text_file,
    replace_approved_lines,
    write_approved_artifact,
)

BODY = "alpha\nbeta\ngamma\ndelta\nepsilon\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write_approved_artifact(tmp_path, "app/a.js", BODY)
    return tmp_path


def test_it_names_the_line_the_text_moved_to(project: Path):
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(project, "app/a.js", 2, 2, "X", "delta")

    message = str(caught.value)
    assert "It is line 4 now" in message
    assert "2 lines further down" in message
    assert "start_line=4" in message
    assert "do not need to read the file again" in message


def test_it_says_which_way_the_text_moved(project: Path):
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(project, "app/a.js", 4, 4, "X", "beta")

    assert "It is line 2 now, 2 lines further up" in str(caught.value)


def test_one_line_is_not_plural(project: Path):
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(project, "app/a.js", 2, 2, "X", "gamma")

    assert "1 line further down" in str(caught.value)


def test_text_that_is_gone_is_said_to_be_gone(project: Path):
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(project, "app/a.js", 2, 2, "X", "not in this file")

    message = str(caught.value)
    assert "not in the file at all now" in message
    assert "Read the file again" in message


def test_several_copies_are_all_named(tmp_path: Path):
    write_approved_artifact(tmp_path, "app/b.js", "x\nsame\ny\nsame\nz\nsame\n")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(tmp_path, "app/b.js", 1, 1, "X", "same")

    message = str(caught.value)
    assert "appears 3 times now" in message
    assert "lines 2, 4, 6" in message


def test_nothing_is_written_when_the_number_is_stale(project: Path):
    with pytest.raises(RepositoryToolError):
        replace_approved_lines(project, "app/a.js", 2, 2, "X", "delta")

    assert read_text_file(project, "app/a.js") == BODY


def test_the_advice_it_gives_actually_works(project: Path):
    """The whole point: the next call has to succeed without a read."""
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(project, "app/a.js", 2, 2, "X", "delta")
    assert "start_line=4" in str(caught.value)

    result = replace_approved_lines(project, "app/a.js", 4, 4, "DELTA", "delta")

    assert result["status"] == "edited"
    assert read_text_file(project, "app/a.js") == "alpha\nbeta\ngamma\nDELTA\nepsilon\n"


def test_whitespace_is_still_ignored_when_matching(project: Path):
    """Unchanged behaviour: the argument's own contract."""
    assert replace_approved_lines(project, "app/a.js", 3, 3, "X", "   gamma  ")["status"]
