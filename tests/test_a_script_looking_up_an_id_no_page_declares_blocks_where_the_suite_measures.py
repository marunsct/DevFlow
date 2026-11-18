"""A script that looks up an element id no page declares is a proven defect, even where an acceptance suite measures.

Measured on one web run: `index.html` declared `<form id="add-form">` and `main.js` looked up `add-task-form`, so the
submit handler was never attached and 40 of 46 acceptance tests failed after drafting. The check that reads it existed,
but where a locked suite measures behaviour only mechanical checks are handed to the test round as proven, and this
one was graded a hint: it also reported ids the script writes in its own markup (`<input id="edit-title-input">` in
the template that builds the inline editor), so it was not exact enough to block. Both halves are fixed: an id a
script writes is declared, and a literal id lookup against pages and scripts is a mechanical check.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import integration_checks as ic

PAGE = """<!DOCTYPE html>
<html><body>
<form id="add-form"><input id="title-input"></form>
<ul id="task-list"></ul>
<script type="module" src="src/main.js"></script>
</body></html>
"""

SCRIPT = """
export function init() {
  const form = document.getElementById('add-task-form');
  if (form) form.addEventListener('submit', () => {});
  document.getElementById('task-list').innerHTML = `<li><input type="text" id="edit-title-input"></li>`;
  const editor = document.getElementById('edit-title-input');
  for (const b of document.querySelectorAll('[data-filter]')) b.dataset.filter;
}
"""


def _project(tmp_path: Path, script: str = SCRIPT) -> Path:
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "index.html").write_text(PAGE)
    (tmp_path / "app" / "src" / "main.js").write_text(script)
    return tmp_path


def test_an_id_the_script_writes_in_its_own_markup_is_declared(tmp_path):
    root = _project(tmp_path)

    found = ic._hooks_javascript_reaches_for(ic._source_files(root), root)  # noqa: SLF001

    assert not [f for f in found if "edit-title-input" in f]
    assert [f for f in found if "`add-task-form`" in f]


def test_an_id_no_page_declares_is_proven_where_the_suite_measures(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr(ic, "_behaviour_is_measured", lambda _root: True)

    proven = ic.problems_that_break_the_product(str(root))

    assert [p for p in proven if "`add-task-form`" in p]
    assert not [p for p in proven if "edit-title-input" in p]
    assert not [p for p in proven if "data-filter" in p], "a data attribute nothing sets stays a hint"


def test_a_page_whose_ids_all_resolve_proves_nothing(tmp_path, monkeypatch):
    root = _project(tmp_path, SCRIPT.replace("'add-task-form'", "'add-form'"))
    monkeypatch.setattr(ic, "_behaviour_is_measured", lambda _root: True)

    assert not [p for p in ic.problems_that_break_the_product(str(root)) if "element id" in p]
