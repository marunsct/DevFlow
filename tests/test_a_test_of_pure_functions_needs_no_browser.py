"""A unit test of a module's DOM-free functions is not told to become a browser test.

One run's `logic.test.mjs` imported `createTask`, `editTask` and two
serialisers from an `app.js` whose render path uses `document`. None of those
four touches the DOM, and the tests passed; but every edit to the file came back
with "You MUST write a browser-based test using Playwright", beside a Playwright
suite the project already had. The note looked at the module, not at what the
test took from it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.test_discovery import _function_bodies, a_test_that_needs_a_dom

APP = """\
export function createTask(title, description = '') {
  return { id: String(Date.now()), title: title.trim(), description, completed: false };
}

export function editTask(tasks, id, title) {
  return tasks.map((t) => (t.id === id ? { ...t, title } : t));
}

export const serialize = (tasks) => JSON.stringify(tasks);

export function renderTasks(tasks) {
  const list = document.getElementById('task-list');
  list.replaceChildren(...tasks.map((t) => { const li = document.createElement('li'); li.textContent = t.title; return li; }));
}

export function addTask(tasks, title) {
  const next = [...tasks, createTask(title)];
  renderTasks(next);
  return next;
}

export function init() {
  renderTasks([]);
}

if (typeof document !== 'undefined') { init(); }
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app.js").write_text(APP, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    return tmp_path


def _note(project: Path, imports: str) -> str | None:
    test = f"import {{ test }} from 'node:test';\n{imports}\ntest('x', () => {{}});\n"
    return a_test_that_needs_a_dom("tests/logic.test.mjs", test, project / "tests")


class TestWhatIsNotFlagged:
    def test_the_run_s_imports(self, project: Path) -> None:
        """The regression."""
        assert _note(project, "import { createTask, editTask, serialize } from '../app.js';") is None

    def test_an_aliased_import(self, project: Path) -> None:
        assert _note(project, "import { createTask as make } from '../app.js';") is None


class TestWhatIsStillFlagged:
    def test_a_function_that_uses_the_dom(self, project: Path) -> None:
        assert "document" in _note(project, "import { renderTasks } from '../app.js';")

    def test_one_that_reaches_it_through_another(self, project: Path) -> None:
        """`addTask` never names `document`; the render it calls does."""
        assert _note(project, "import { addTask } from '../app.js';") is not None

    def test_a_namespace_import_is_assumed_to_reach_everything(self, project: Path) -> None:
        assert _note(project, "import * as app from '../app.js';") is not None

    def test_a_name_that_is_not_a_readable_function(self, project: Path) -> None:
        """Unknown is not safe; the old behaviour stands."""
        assert _note(project, "import { Store } from '../app.js';") is not None

    def test_a_test_that_provides_a_dom_is_left_alone(self, project: Path) -> None:
        assert _note(project, "import { JSDOM } from 'jsdom';\nimport { renderTasks } from '../app.js';") is None


class TestReadingTheBodies:
    def test_each_kind_of_function_is_found(self) -> None:
        bodies = _function_bodies(APP)

        assert {"createTask", "editTask", "serialize", "renderTasks", "addTask", "init"} <= set(bodies)

    def test_a_body_ends_at_its_own_brace(self) -> None:
        """Braces inside strings and nested blocks do not end it early."""
        body = _function_bodies("function f() { const s = '}'; if (x) { y(); } return 1; }\nfunction g() {}")["f"]

        assert body.endswith("return 1; }")
