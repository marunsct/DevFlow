"""A range whose `expect_end` is right and whose `end_line` is a line off is
applied to the line the pin names.

Measured on one run: `expect_end="});"` with `end_line=24` for a listener
whose `});` is line 25. The pin was right and the count one short; the edit was
refused twice in one stage for unbalanced brackets, and the same shape a dozen
times across the sprint.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

UI = """\
export function render(tasks, list) {
  tasks.forEach(task => {
    const checkbox = document.createElement('input');
    checkbox.addEventListener('change', () => {
      toggleTask(task.id);
      render();
    });
    list.appendChild(checkbox);
  });
}
"""

LISTENER = (
    "    checkbox.addEventListener('click', () => {\n"
    "      toggleTask(task.id);\n"
    "      render();\n"
    "    });"
)


def test_an_end_one_short_of_its_pin_is_taken_to_the_pin(tmp_path) -> None:
    (tmp_path / "ui.js").write_text(UI, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "ui.js", 4, 6, LISTENER,
        expect_start="checkbox.addEventListener('change', () => {", expect_end="});",
    )

    written = (tmp_path / "ui.js").read_text(encoding="utf-8")
    assert "addEventListener('click'" in written and "'change'" not in written
    assert written.count("});") == 2
    assert "Replaced lines 4-7 of 10, not 4-6" in result["detail"]
    assert "`expect_end` names line 7" in result["detail"]


def test_an_edit_that_parses_as_sent_is_applied_as_sent(tmp_path) -> None:
    """The pin is consulted only for an edit already refused: `});` closes many
    blocks, and a range that leaves the file sound is not second-guessed."""
    (tmp_path / "ui.js").write_text(UI, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "ui.js", 4, 8, LISTENER,
        expect_start="checkbox.addEventListener('change', () => {", expect_end="});",
    )

    assert "Replaced lines 4-8 of 10." in result["detail"]


def test_an_end_that_is_where_its_pin_says_is_left_alone(tmp_path) -> None:
    (tmp_path / "ui.js").write_text(UI, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "ui.js", 4, 7, LISTENER,
        expect_start="checkbox.addEventListener('change', () => {", expect_end="});",
    )

    assert "Replaced lines 4-7 of 10." in result["detail"]


def test_with_no_pin_nearby_the_edit_is_still_refused(tmp_path) -> None:
    (tmp_path / "ui.js").write_text(UI, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(
            tmp_path, "ui.js", 4, 6, LISTENER,
            expect_start="checkbox.addEventListener('change', () => {", expect_end="nothing like this",
        )

    assert "cannot parse" in str(caught.value)
    assert (tmp_path / "ui.js").read_text(encoding="utf-8") == UI
