"""A range whose two line numbers are both off is applied where its pins are.

Measured on one run: `start_line=22, end_line=29` for a block whose first line
was 18 and whose last was 22, both pinned exactly. The refusal said "send the
same call with start_line=18 and end_line adjusted by the same amount", which
would have replaced three lines too many.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

SUITE = """\
import { getTasks } from './script.js';

test('adds a task', () => {
  expect(getTasks().length).toBe(1);
});

test('returns a copy', () => {
  // mutating the returned array does not affect the internal one
  const tasks = getTasks();
  tasks[0].title = 'Changed';
  expect(getTasks()[0].title).not.toBe('Changed');
});

test('persists', () => {
  expect(localStorage.getItem('tasks')).not.toBeNull();
});
"""

NEW_BODY = "  // the list handed out is a copy\n  expect(getTasks()).not.toBe(getTasks());"


def test_both_ends_are_taken_from_their_pins(tmp_path) -> None:
    (tmp_path / "script.test.js").write_text(SUITE, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "script.test.js", 12, 19, NEW_BODY,
        expect_start="// mutating the returned array does not affect the internal one",
        expect_end="expect(getTasks()[0].title).not.toBe('Changed');",
    )

    written = (tmp_path / "script.test.js").read_text(encoding="utf-8")
    assert "tasks[0].title = 'Changed'" not in written
    assert "test('persists'" in written, "nothing past the end pin was taken"
    assert "Lines 8-11 were replaced, not 12-19" in result["detail"]


def test_an_end_pin_on_several_lines_settles_nothing(tmp_path) -> None:
    (tmp_path / "script.test.js").write_text(SUITE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(
            tmp_path, "script.test.js", 12, 19, NEW_BODY,
            expect_start="// mutating the returned array does not affect the internal one",
            expect_end="});",
        )

    assert "is not what you expected" in str(caught.value)
    assert (tmp_path / "script.test.js").read_text(encoding="utf-8") == SUITE


def test_with_no_end_pin_the_stage_is_told_where_the_line_is(tmp_path) -> None:
    (tmp_path / "script.test.js").write_text(SUITE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(
            tmp_path, "script.test.js", 12, 19, NEW_BODY,
            expect_start="// mutating the returned array does not affect the internal one",
        )

    assert "It is line 8 now" in str(caught.value)
