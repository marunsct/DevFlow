"""A pin that leaves off the end of its line still finds the line.

Measured on one run, nine refusals in one sprint. `expect_start` was a first
line shortened and closed with `...`, at the right line number; and
`function resetStorage()` for `function resetStorage() {` a few lines from
where it was asked for. Both were told the line "is not in the file at all".
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

SUITE = """\
// state_and_persistence_module.test.js
import assert from 'assert';

const STORAGE_KEY = 'simple-todo-list';

function resetStorage() {
  globalThis.localStorage = {};
}
"""


def test_a_pin_ended_with_an_ellipsis_pins_its_line(tmp_path) -> None:
    (tmp_path / "suite.test.js").write_text(SUITE, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "suite.test.js", 1, 1, "// the suite for state and persistence",
        expect_start="// state_and_persist...",
    )

    assert result["status"] == "edited"
    assert (tmp_path / "suite.test.js").read_text(encoding="utf-8").startswith("// the suite for state")


def test_a_shortened_pin_at_the_wrong_line_is_told_where_the_line_is(tmp_path) -> None:
    (tmp_path / "suite.test.js").write_text(SUITE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(
            tmp_path, "suite.test.js", 4, 6, "function resetStorage() {\n  globalThis.localStorage = null;\n}",
            expect_start="function resetStorage()",
        )

    message = str(caught.value)
    assert "It is line 6 now" in message
    assert "not in the file at all" not in message
    assert (tmp_path / "suite.test.js").read_text(encoding="utf-8") == SUITE


def test_a_spread_is_not_an_ellipsis_to_strip(tmp_path) -> None:
    """`...` on its own, or opening a line, is code."""
    (tmp_path / "suite.test.js").write_text(SUITE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(tmp_path, "suite.test.js", 2, 2, "import a from 'a';", expect_start="...")

    assert "not in the file at all" in str(caught.value)
