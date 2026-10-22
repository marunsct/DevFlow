"""Handlers that change the state and never redraw, beside handlers that do.

One completed run's `ui.js` redrew after add and filter, and after delete,
edit and toggle did not: a deleted task stayed on screen until the next add.
Every suite passed and the review accepted.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import (
    _a_change_the_page_never_shows,
    _responsive_css_the_page_cannot_use,
    _source_files,
    summarise_integration,
)

UI = """import { getVisibleTasks, setFilter, addTask, deleteTask, toggleComplete } from './state.js';

let listEl, form;

function render() {
  listEl.innerHTML = '';
  getVisibleTasks().forEach(t => {
    const li = document.createElement('li');
    const box = document.createElement('input');
    box.addEventListener('change', () => toggleComplete(t.id));
    const del = document.createElement('button');
    del.onclick = () => deleteTask(t.id);
    li.append(box, del);
    listEl.appendChild(li);
  });
}

export function init() {
  listEl = document.getElementById('list');
  form = document.getElementById('form');
  document.querySelectorAll('.filter').forEach(b => b.addEventListener('click', () => { setFilter(b.dataset.f); render(); }));
  form.addEventListener('submit', e => { e.preventDefault(); addTask('x'); render(); });
  render();
}
"""


def _project(tmp_path: Path, ui: str) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "ui.js").write_text(ui, encoding="utf-8")
    (app / "state.js").write_text("export function addTask() {}\n", encoding="utf-8")
    return tmp_path


def test_the_actions_that_never_redraw_are_named(tmp_path: Path) -> None:
    root = _project(tmp_path, UI)

    (problem,) = _a_change_the_page_never_shows(_source_files(root), root)

    assert "`toggleComplete`, `deleteTask`" in problem or "`deleteTask`, `toggleComplete`" in problem
    assert "never call `render()`" in problem


def test_it_blocks(tmp_path: Path) -> None:
    root = _project(tmp_path, UI)

    assert "never call `render()`" in summarise_integration(root).split("DOES NOT WORK")[1].split("untidy")[0]


def test_every_handler_redrawing_is_left_alone(tmp_path: Path) -> None:
    ui = UI.replace("() => toggleComplete(t.id)", "() => { toggleComplete(t.id); render(); }").replace(
        "() => deleteTask(t.id)", "() => { deleteTask(t.id); render(); }"
    )
    root = _project(tmp_path, ui)

    assert _a_change_the_page_never_shows(_source_files(root), root) == []


def test_a_page_that_redraws_on_every_change_is_left_alone(tmp_path: Path) -> None:
    root = _project(tmp_path, UI + "\nsubscribe(render);\n")

    assert _a_change_the_page_never_shows(_source_files(root), root) == []


PAGE = '<html><head><link rel="stylesheet" href="styles.css"></head><body></body></html>\n'
SHEET = "@media (max-width: 600px) { body { padding: 0 } }\n"


def _responsive(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "index.html").write_text(PAGE, encoding="utf-8")
    (app / "styles.css").write_text(SHEET, encoding="utf-8")
    return tmp_path


def test_a_missing_viewport_misses_a_brief_that_asks_for_mobile(tmp_path: Path) -> None:
    root = _responsive(tmp_path)
    brief = "## Acceptance Criteria\n- Responsive design for mobile and desktop\n"

    summary = summarise_integration(root, None, brief)

    assert "viewport" in summary.split("a stated acceptance criterion this product does not meet")[1]


def test_without_such_a_brief_it_stays_untidy(tmp_path: Path) -> None:
    root = _responsive(tmp_path)

    (problem,) = _responsive_css_the_page_cannot_use(_source_files(root), root, "Build a list.")

    assert "stated criterion" not in problem
