"""Where a locked acceptance suite measures behaviour, only mechanical checks block.

An inference from code patterns ("this control does nothing") is a hint for the
reviewers there; a mechanical fact (a page loading a script that does not
exist) still breaks the product. Without a suite, every check is as it was.
"""

from __future__ import annotations

from pathlib import Path

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.analysis.integration_checks import (
    _CHECKS,
    _MECHANICAL,
    problems_that_break_the_product,
    summarise_integration,
)

#: Delete and toggle change the state and never redraw.
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

#: A page that loads a script that is not there (mechanical), and a script
#: whose delete and toggle never redraw (inferred).
PAGE = (
    '<!DOCTYPE html><html><body><ul id="list"></ul><form id="form"></form>'
    '<script type="module" src="ui.js"></script>'
    '<script type="module" src="missing.js"></script>'
    '</body></html>'
)


def _product(root: Path) -> None:
    app = root / "notes"
    app.mkdir(parents=True)
    (app / "index.html").write_text(PAGE)
    (app / "ui.js").write_text(UI)
    (app / "state.js").write_text("export function addTask() {}\n")


def _lock(root: Path) -> None:
    (root / ".project-directory").write_text("notes\n")
    suite.save_criteria(root, [Criterion("AC-1", "Save a note", "brief")])
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] saves', ()=>{});\n")
    suite.lock(root)


def test_without_a_suite_the_checks_are_as_they_were(tmp_path) -> None:
    _product(tmp_path)
    breaking = problems_that_break_the_product(tmp_path)
    assert any("missing.js" in p for p in breaking)
    assert "hint" not in summarise_integration(tmp_path)


def test_with_a_locked_suite_only_mechanical_findings_block(tmp_path) -> None:
    _product(tmp_path)
    before = problems_that_break_the_product(tmp_path)
    _lock(tmp_path)

    after = problems_that_break_the_product(tmp_path)

    assert any("missing.js" in p for p in after)
    inferred = [p for p in before if p not in after]
    assert inferred, "the fixture should trip an inferred check too"
    summary = summarise_integration(tmp_path)
    hints = summary.index("from reading code patterns")
    assert all(summary.index(p) > hints for p in inferred)
    assert summary.index(next(p for p in after if "missing.js" in p)) < hints


def test_every_mechanical_check_is_a_registered_one() -> None:
    names = {entry[0] for entry in _CHECKS}
    assert _MECHANICAL <= names
    # Most checks infer behaviour; the suite measures it.
    assert len(_MECHANICAL) < len(names)
