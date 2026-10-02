"""`replace_lines` at the line after the last one adds to the end of the file.

Measured on two runs. A fix stage with a 114-line file sent `start_line 115,
end_line 114` and was told that "is not a range"; sent `start_line 115` and was
told "line 115 does not exist"; and fell back to an `edit_artifact` whose
`find` matched 44 times. It meant one thing each time: add these lines at the
end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    replace_approved_lines,
    write_approved_artifact,
)

MODULE = "export function add(a, b) {\n  return a + b;\n}\n"
MORE = "\nexport function sub(a, b) {\n  return a - b;\n}\n"


def _project(root: Path) -> Path:
    write_approved_artifact(root, "app/package.json", '{"name": "app", "type": "module"}')
    write_approved_artifact(root, "app/logic.js", MODULE)
    return root / "app" / "logic.js"


@pytest.mark.parametrize("end_line", [3, 4])
def test_the_line_after_the_last_is_where_lines_are_added(tmp_path: Path, end_line: int) -> None:
    target = _project(tmp_path)

    result = replace_approved_lines(tmp_path, "app/logic.js", 4, end_line, MORE)

    assert target.read_text(encoding="utf-8") == MODULE + MORE
    assert "Added 4 lines after line 3, the last line" in str(result)


def test_a_file_with_no_final_newline_does_not_run_the_lines_together(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "app/package.json", '{"name": "app", "type": "module"}')
    write_approved_artifact(tmp_path, "app/notes.txt", "one\ntwo")

    replace_approved_lines(tmp_path, "app/notes.txt", 3, 3, "three")

    assert (tmp_path / "app" / "notes.txt").read_text(encoding="utf-8") == "one\ntwo\nthree\n"


def test_a_pin_on_the_last_line_is_an_anchor_and_is_accepted(tmp_path: Path) -> None:
    target = _project(tmp_path)

    replace_approved_lines(tmp_path, "app/logic.js", 4, 4, MORE, expect_start="}")

    assert target.read_text(encoding="utf-8") == MODULE + MORE


def test_a_pin_that_is_not_the_last_line_means_the_numbers_are_stale(tmp_path: Path) -> None:
    target = _project(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(
            tmp_path, "app/logic.js", 4, 4, MORE, expect_start="export function mul(a, b) {",
        )

    assert "would add your `content` at the end of the file" in str(refused.value)
    assert target.read_text(encoding="utf-8") == MODULE


def test_further_past_the_end_is_still_refused(tmp_path: Path) -> None:
    target = _project(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(tmp_path, "app/logic.js", 9, 9, MORE)

    assert "line 9 does not exist" in str(refused.value)
    assert target.read_text(encoding="utf-8") == MODULE


def test_added_lines_that_break_the_file_are_refused_like_any_edit(tmp_path: Path) -> None:
    target = _project(tmp_path)

    with pytest.raises(RepositoryToolError):
        replace_approved_lines(tmp_path, "app/logic.js", 4, 4, "export function broken( {\n")

    assert target.read_text(encoding="utf-8") == MODULE
