"""A `replace_lines` whose content repeats the lines around its range is applied
to the range it was written for.

Measured on one run: 24 edits were refused for breaking the file they changed.
Most had the same shape - a `content` that opened with the line above its
range, or closed with the lines below it, so replacing only the stated range
wrote those lines twice. One sent

    export default {
        testEnvironment: 'jest-environment-jsdom',
        transform: {},
    };

for lines 1-4 of a six-line file whose lines 5 and 6 were `transform: {},` and
`};`, was told the brackets did not balance, and sent three more edits and a
whole-file write to the same four lines.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _the_range_its_content_overlaps,
    replace_approved_lines,
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

CONFIG = """\
export default {
  extensionsToTreatAsEsm: ['.js'],

  testEnvironment: 'jest-environment-jsdom',
  transform: {},
};
"""

STORE = """\
class Store {
  on(event, callback) {
    if (event === 'stateChange') {
      this.listen(event, callback);
    }
  }
}

export default new Store();
"""


def test_content_that_ends_with_the_lines_below_its_range(tmp_path) -> None:
    (tmp_path / "jest.config.js").write_text(CONFIG, encoding="utf-8")
    content = "export default {\n    testEnvironment: 'jest-environment-jsdom',\n    transform: {},\n};"

    result = replace_approved_lines(tmp_path, "jest.config.js", 1, 4, content)

    assert result["status"] == "edited"
    assert (tmp_path / "jest.config.js").read_text(encoding="utf-8") == content + "\n"
    assert "Replaced lines 1-6 of 6, not 1-4" in result["detail"]
    assert "ends with the 2 lines just below it" in result["detail"]


def test_content_that_opens_with_the_line_above_and_closes_with_the_one_below(tmp_path) -> None:
    (tmp_path / "store.js").write_text(STORE, encoding="utf-8")
    content = (
        "  on(event, callback) {\n"
        "    if (event === 'stateChange') {\n"
        "      this.listen(event, callback);\n"
        "      callback(this.state);\n"
        "    }\n"
        "  }"
    )

    result = replace_approved_lines(tmp_path, "store.js", 3, 5, content)

    written = (tmp_path / "store.js").read_text(encoding="utf-8")
    assert written.count("on(event, callback) {") == 1
    assert "callback(this.state);" in written
    assert "opens with the 1 line just above that range" in result["detail"]
    assert "ends with the 1 line just below it" in result["detail"]


def test_an_edit_that_works_as_sent_is_left_as_sent(tmp_path) -> None:
    """A closing brace that really is being added is not taken for an overlap."""
    (tmp_path / "store.js").write_text(STORE, encoding="utf-8")
    content = "      this.listen(event, callback);\n      if (callback) {\n        callback();\n      }"

    result = replace_approved_lines(tmp_path, "store.js", 4, 4, content)

    assert "Replaced lines 4-4 of 9." in result["detail"]


def test_an_edit_that_is_broken_whichever_range_is_meant_is_still_refused(tmp_path) -> None:
    (tmp_path / "store.js").write_text(STORE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(tmp_path, "store.js", 3, 4, "    if (event === {\n    }\n  }")

    assert "cannot parse" in str(caught.value)
    assert (tmp_path / "store.js").read_text(encoding="utf-8") == STORE


def test_blank_lines_alone_are_not_an_overlap(tmp_path) -> None:
    lines = ["a();\n", "\n", "\n", "b();\n"]

    assert _the_range_its_content_overlaps(tmp_path / "x.js", lines, 1, 1, "a(;\n\n", "x.js") is None
