"""Two findings handed to a test round as proven, against working code.

One run's `test_round_1` was told, as facts "decided by comparing two files in
this workspace, not by judgement":

    - todo-app/app.js reads the attribute `data-id`, which no HTML element sets.
    - This sprint's plan names `filtered.map` and the workspace has no file of
      that name anywhere. ... Write it, or say in your report why the plan ...

`render()` wrote `data-id="${task.id}"` into every row it built, and the plan
said "right before the `filtered.map()` call". A `defect_fix` stage then spent
its calls trying to edit the plan document to make the second one go away.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import _hooks_javascript_reaches_for, _source_files
from app.analysis.planned_files import paths_a_plan_named

PAGE = """<!DOCTYPE html>
<html><body>
<ul id="task-list"></ul>
<script type="module" src="app.js"></script>
</body></html>
"""

APP = """\
export function render(filtered) {
  const taskList = document.getElementById('task-list');
  taskList.innerHTML = filtered.map(task => `
    <li class="task-item" data-id="${task.id}">${task.title}</li>`).join('');
}

document.getElementById('task-list').addEventListener('click', (event) => {
  const item = event.target.closest('.task-item');
  if (item) remove(item.dataset.id);
});
"""


def _hooks(tmp_path: Path, script: str) -> list[str]:
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "app.js").write_text(script, encoding="utf-8")
    return _hooks_javascript_reaches_for(_source_files(tmp_path), tmp_path)


class TestAnAttributeTheScriptWritesIntoMarkup:
    def test_the_run_s_render_is_not_reported(self, tmp_path) -> None:
        assert not [p for p in _hooks(tmp_path, APP) if "data-id" in p]

    def test_escaped_quotes_in_a_plain_string_count_too(self, tmp_path) -> None:
        script = APP.replace(
            "`\n    <li class=\"task-item\" data-id=\"${task.id}\">${task.title}</li>`",
            "'<li class=\"task-item\" data-id=\\'' + task.id + '\\'>' + task.title + '</li>'",
        )

        assert not [p for p in _hooks(tmp_path, script) if "data-id" in p]

    def test_an_attribute_nothing_writes_is_still_reported(self, tmp_path) -> None:
        """The check's own case: a read with no writer anywhere."""
        script = APP.replace("data-id", "data-key")

        assert [p for p in _hooks(tmp_path, script) if "data-id" in p]

    def test_a_selector_is_a_read_not_a_write(self, tmp_path) -> None:
        """`[data-id="3"]` has the same `data-id="` shape and sets nothing."""
        script = (
            "const row = document.querySelector('[data-id=\"3\"]');\n"
            "document.getElementById('task-list');\n"
        )

        assert [p for p in _hooks(tmp_path, script) if "data-id" in p]


class TestACallIsNotAPlannedFile:
    def test_the_run_s_sentence(self) -> None:
        plan = (
            "(6) Add this exact one-line comment inside render(), right before "
            "the filtered.map() call: '// NOTE: ...'"
        )

        assert "filtered.map" not in paths_a_plan_named([plan])

    def test_a_real_source_map_is_still_a_file(self) -> None:
        assert paths_a_plan_named(["Ship app.js.map beside the bundle."]) == ["app.js.map"]

    def test_a_file_followed_by_a_parenthetical_is_still_a_file(self) -> None:
        """Prose puts a note in brackets after a name, with a space. A call has
        its parenthesis attached, so only that is read as one."""
        assert "index.html" in paths_a_plan_named(["Create index.html (the page)."])
