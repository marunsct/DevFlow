"""A `replace_lines` pin copied with the harness's own line-number gutter still pins.

This module quotes files back as `   93 | text`. One run's `specialist_ui_ux_0`
sent `expect_start=" 1 | export class TaskItem extends HTMLElement{"` for a
line reading `export class TaskItem extends HTMLElement{`, and was refused as
stale by the tool whose quoting it had copied.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, _without_a_copied_gutter, replace_approved_lines

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

ITEM = """export class TaskItem extends HTMLElement{
  constructor(){super();}
}
"""


def test_the_run_s_call_is_applied(tmp_path) -> None:
    (tmp_path / "task-item.js").write_text(ITEM, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "task-item.js", 1, 1,
        "import { escapeHTML } from './app.js';\nexport class TaskItem extends HTMLElement{",
        expect_start=" 1 | export class TaskItem extends HTMLElement{",
    )

    assert result["status"] == "edited"
    assert (tmp_path / "task-item.js").read_text(encoding="utf-8").startswith("import { escapeHTML }")


def test_both_ends_and_the_nearest_line_marker_are_forgiven() -> None:
    lines = ["a = 1\n", "b = 2\n"]

    assert _without_a_copied_gutter(">    2 | b = 2", lines) == "b = 2"
    assert _without_a_copied_gutter("  1 | a = 1\n  2 | b = 2", lines) == "a = 1\nb = 2"


def test_a_line_that_really_starts_with_a_number_is_compared_as_written() -> None:
    lines = ["404 Not Found\n", "200 OK\n"]

    assert _without_a_copied_gutter("404 Not Found", lines) == "404 Not Found"


def test_a_pin_without_a_gutter_is_untouched() -> None:
    assert _without_a_copied_gutter("export const x = 1;", ["y\n"]) == "export const x = 1;"


def test_a_wrong_pin_is_still_refused(tmp_path) -> None:
    (tmp_path / "task-item.js").write_text(ITEM, encoding="utf-8")

    with pytest.raises(RepositoryToolError, match="not what you expected"):
        replace_approved_lines(
            tmp_path, "task-item.js", 1, 1, "// x",
            expect_start=" 1 | export class SomethingElse {",
        )
