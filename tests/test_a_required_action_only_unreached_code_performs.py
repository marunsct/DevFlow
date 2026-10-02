"""A required action whose only code nothing in the product uses is reported.

Measured on one completed run: the brief says users can add, edit and delete
tasks and filter them. `src/business.js` exported `editTask`, `deleteTask` and
`filterTasks`, each unit tested; `app.js`, the one script the page loads,
imported `addTask` and nothing else. Twelve of twelve tests passed and the last
review accepted a product in which a task can only be added.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import _a_required_action_only_unreached_code_performs

BRIEF = (
    "# Brief\n\n## Acceptance Criteria\n"
    "- Users can add, edit, delete tasks\n"
    "- Filter functionality works correctly\n"
)

BUSINESS = (
    "export function addTask(tasks, title) { return [...tasks, { title }]; }\n"
    "export function editTask(tasks, id, title) { return tasks; }\n"
    "export function deleteTask(tasks, id) { return tasks; }\n"
)

PAGE = '<!DOCTYPE html><html><body><form id="f"></form><script type="module" src="app.js"></script></body></html>\n'

ONLY_ADDS = "import { addTask } from './src/business.js';\ndocument.getElementById('f').onsubmit = () => addTask([], 'x');\n"

DOES_ALL_THREE = (
    "import { addTask, editTask, deleteTask } from './src/business.js';\n"
    "list.onclick = e => e.target.matches('.edit') ? editTask([], 1, 'y') : deleteTask([], 1);\n"
    "form.onsubmit = () => addTask([], 'x');\n"
)


def _project(tmp_path: Path, app: str, page: str = PAGE) -> list[Path]:
    project = tmp_path / "app"
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "index.html").write_text(page, encoding="utf-8")
    (project / "app.js").write_text(app, encoding="utf-8")
    (project / "src" / "business.js").write_text(BUSINESS, encoding="utf-8")
    (project / "tests" / "business.test.js").write_text(
        "import { editTask, deleteTask } from '../src/business.js';\n", encoding="utf-8"
    )
    return sorted(p for p in project.rglob("*") if p.is_file())


def test_actions_only_an_unused_export_performs_are_reported(tmp_path) -> None:
    found = _a_required_action_only_unreached_code_performs(_project(tmp_path, ONLY_ADDS), tmp_path, BRIEF)

    reported = " ".join(found)
    assert "be able to `edit`" in reported and "`editTask` in app/src/business.js" in reported
    assert "be able to `delete`" in reported and "`deleteTask` in app/src/business.js" in reported
    assert "be able to `add`" not in reported
    assert "nothing the page loads imports or calls" in reported


def test_a_product_that_wires_them_up_is_silent(tmp_path) -> None:
    assert _a_required_action_only_unreached_code_performs(
        _project(tmp_path, DOES_ALL_THREE), tmp_path, BRIEF
    ) == []


def test_a_test_that_uses_the_export_does_not_make_it_reached(tmp_path) -> None:
    """The fixture's test file imports both. They are still unreached."""
    found = _a_required_action_only_unreached_code_performs(_project(tmp_path, ONLY_ADDS), tmp_path, BRIEF)

    assert len(found) == 2


def test_without_a_page_exports_are_the_product(tmp_path) -> None:
    files = [p for p in _project(tmp_path, ONLY_ADDS) if p.suffix != ".html"]

    assert _a_required_action_only_unreached_code_performs(files, tmp_path, BRIEF) == []


def test_an_action_another_script_performs_its_own_way_is_silent(tmp_path) -> None:
    app = ONLY_ADDS + "function deleteRow(id) {}\nfunction editInline(id) {}\nlist.onclick = () => { deleteRow(1); editInline(1); };\n"

    assert _a_required_action_only_unreached_code_performs(_project(tmp_path, app), tmp_path, BRIEF) == []
