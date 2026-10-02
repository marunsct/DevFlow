"""A handler waiting on the product's own event, which nothing sends, is reported.

Measured on one completed run: `app.js` listened for `taskEdited`, "dispatched
from ui.js double-click" by its comment. `ui.js` dispatched nothing. There was
no way to edit a task in a product whose brief says users can; every suite
passed and the last review accepted it.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.integration_checks import _a_listener_for_an_event_nothing_dispatches

APP = """\
import { editTask } from './model.js';

document.getElementById('task-list').addEventListener('click', e => {});

// Listen for custom edit event dispatched from ui.js double-click
document.addEventListener('taskEdited', e => {
  editTask(e.detail.id, e.detail.title);
});
"""

UI_THAT_SENDS_NOTHING = "export function render(state) { /* builds the list */ }\n"

UI_THAT_SENDS_IT = (
    "span.addEventListener('dblclick', () => {\n"
    "  document.dispatchEvent(new CustomEvent('taskEdited', { detail: { id, title } }));\n"
    "});\n"
)


def _project(tmp_path: Path, ui: str) -> list[Path]:
    project = tmp_path / "app"
    project.mkdir()
    (project / "app.js").write_text(APP, encoding="utf-8")
    (project / "ui.js").write_text(ui, encoding="utf-8")
    return sorted(project.glob("*.js"))


def test_an_event_nothing_sends_is_reported_with_its_line(tmp_path) -> None:
    found = _a_listener_for_an_event_nothing_dispatches(_project(tmp_path, UI_THAT_SENDS_NOTHING), tmp_path)

    assert len(found) == 1
    assert "app/app.js line 6 listens for `taskEdited`" in found[0]
    assert "cannot be reached by a user" in found[0]


def test_an_event_something_sends_is_fine(tmp_path) -> None:
    assert _a_listener_for_an_event_nothing_dispatches(_project(tmp_path, UI_THAT_SENDS_IT), tmp_path) == []


def test_the_browser_s_own_events_are_never_questioned(tmp_path) -> None:
    files = _project(tmp_path, UI_THAT_SENDS_IT)
    (tmp_path / "app" / "extra.js").write_text(
        "document.addEventListener('DOMContentLoaded', init);\n"
        "form.addEventListener('submit', onSubmit);\n"
        "box.addEventListener('transitionend', done);\n",
        encoding="utf-8",
    )

    assert _a_listener_for_an_event_nothing_dispatches(sorted((tmp_path / "app").glob("*.js")), tmp_path) == []


def test_a_name_made_at_run_time_silences_the_check(tmp_path) -> None:
    """It cannot know what `new CustomEvent(name)` will be called."""
    ui = "export const send = name => document.dispatchEvent(new CustomEvent(name));\n"

    assert _a_listener_for_an_event_nothing_dispatches(_project(tmp_path, ui), tmp_path) == []


def test_an_emitter_that_sends_it_by_name_counts(tmp_path) -> None:
    ui = "bus.emit('taskEdited', { id, title });\n"

    assert _a_listener_for_an_event_nothing_dispatches(_project(tmp_path, ui), tmp_path) == []


def test_an_event_only_a_test_sends_is_still_unsent(tmp_path) -> None:
    files = _project(tmp_path, UI_THAT_SENDS_NOTHING)
    test_file = tmp_path / "app" / "app.test.js"
    test_file.write_text("document.dispatchEvent(new CustomEvent('taskEdited'));\n", encoding="utf-8")

    found = _a_listener_for_an_event_nothing_dispatches([*files, test_file], tmp_path)

    assert len(found) == 1
