"""A field the brief says a record is added with, which nothing on the page collects.

`tests/brief_low.md` asks to "Add new tasks with title and description". Two
runs in a row completed with a data layer that stored a `description` and a page
with one input, for the title. Both milestone reviews accepted, and the suites
passed a description straight to the data layer.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import (
    _a_field_the_brief_asks_for_that_nothing_collects,
    _fields_the_brief_asks_to_add_with,
    _source_files,
    summarise_integration,
)

BRIEF = (Path(__file__).parent / "brief_low.md").read_text(encoding="utf-8")

PAGE = """<!DOCTYPE html>
<html><body>
<form id="newTaskForm">
  <input type="text" id="taskTitle" placeholder="New task" required>
  {extra}
  <button type="submit">Add</button>
</form>
<ul id="taskList"></ul>
<script type="module" src="app.js"></script>
</body></html>
"""

DATA = "export function addTask(title, description = '') { return { title, description }; }\n"


def _product(tmp_path: Path, extra: str = "", script: str = "") -> Path:
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "index.html").write_text(PAGE.format(extra=extra), encoding="utf-8")
    (app / "data.js").write_text(DATA, encoding="utf-8")
    (app / "app.js").write_text(script or "import { addTask } from './data.js';\n", encoding="utf-8")
    (app / "tests" / "data.test.js").write_text(
        "import { addTask } from '../data.js';\naddTask('x', 'a description');\n", encoding="utf-8"
    )
    return tmp_path


def test_the_brief_s_fields_are_read() -> None:
    assert set(_fields_the_brief_asks_to_add_with(BRIEF)) == {"title", "description"}


def test_a_page_with_no_control_for_the_description_is_reported(tmp_path) -> None:
    root = _product(tmp_path)

    problems = _a_field_the_brief_asks_for_that_nothing_collects(_source_files(root), root, BRIEF)

    assert len(problems) == 1
    assert "`description`" in problems[0]
    assert "Add new tasks with title and description" in problems[0]


def test_it_is_graded_as_a_criterion_not_met(tmp_path) -> None:
    root = _product(tmp_path)

    summary = summarise_integration(root, None, BRIEF)

    criterion = summary.split("a stated acceptance criterion this product does not meet")[1]
    assert "`description`" in criterion.split("untidy rather than broken")[0]


def test_a_textarea_for_it_answers_it(tmp_path) -> None:
    root = _product(tmp_path, extra='<textarea id="taskDescription"></textarea>')

    assert _a_field_the_brief_asks_for_that_nothing_collects(_source_files(root), root, BRIEF) == []


def test_a_control_a_script_builds_answers_it(tmp_path) -> None:
    root = _product(
        tmp_path,
        script="const d = document.createElement('textarea');\nd.placeholder = 'Description';\n",
    )

    assert _a_field_the_brief_asks_for_that_nothing_collects(_source_files(root), root, BRIEF) == []


def test_a_brief_that_names_no_fields_asks_nothing(tmp_path) -> None:
    root = _product(tmp_path)

    assert _a_field_the_brief_asks_for_that_nothing_collects(
        _source_files(root), root, "Users can add, edit, delete tasks."
    ) == []


def test_a_lone_text_box_stands_for_the_first_field(tmp_path) -> None:
    """One run's add form was a single `<input type="text" placeholder="New
    task">` - the title, never named. It is not a missing title."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "index.html").write_text(
        '<form><input type="text" placeholder="New task" required><button>Add</button></form>\n'
        '<input type="checkbox" id="done">\n',
        encoding="utf-8",
    )

    problems = _a_field_the_brief_asks_for_that_nothing_collects(_source_files(tmp_path), tmp_path, BRIEF)

    assert [p.split("`")[1] for p in problems] == ["description"]


def test_a_page_with_only_boxes_to_tick_has_no_title_either(tmp_path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "index.html").write_text('<label><input type="checkbox"> Done</label>\n', encoding="utf-8")

    problems = _a_field_the_brief_asks_for_that_nothing_collects(_source_files(tmp_path), tmp_path, BRIEF)

    assert sorted(p.split("`")[1] for p in problems) == ["description", "title"]
