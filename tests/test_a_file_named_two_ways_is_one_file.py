"""A file the specification spelled one way and the project another was "a file nobody is given".

Measured on one run: the specification called the stylesheet `style.css`, the
scaffold had made `styles.css`, and a constraint the sprint plan quoted from the
specification - "index.html + style.css + app.js" - was read as a file the
sprint names that no work order lists. The lead's plan was sent back twice for
it and dispatched unready on the third; giving `style.css` to a work order
would have made a second stylesheet.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis.work_orders import _another_spelling_of, _files_the_sprint_names_and_nobody_is_given


@pytest.mark.parametrize("name, known", [
    ("style.css", {"styles.css"}),
    ("tasks.js", {"task.js"}),
])
def test_another_spelling_of_a_known_file(name, known):
    assert _another_spelling_of(name, known)


@pytest.mark.parametrize("name, known", [
    ("ui.js", {"app.js"}),
    ("model.js", {"app.js", "index.html"}),
    ("storage.js", {"store.js"}),
    ("styles.scss", {"styles.css"}),
    ("app.css", {"app.js"}),
])
def test_a_different_file_is_not_one(name, known):
    assert not _another_spelling_of(name, known)


def _order(*files: str):
    return SimpleNamespace(files=list(files))


def test_the_runs_scope_names_no_file_nobody_is_given(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "styles.css").write_text("body {}\n")
    (project / "index.html").write_text("<!doctype html>\n")
    scope = (
        "styles.css: mobile-first layout\n"
        "The application remains under 500 lines across index.html + style.css + app.js combined."
    )

    unassigned = _files_the_sprint_names_and_nobody_is_given(scope, [_order("app/app.js")], tmp_path, "app")

    assert unassigned == []


def test_a_new_file_nobody_is_given_is_still_named(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "styles.css").write_text("body {}\n")

    unassigned = _files_the_sprint_names_and_nobody_is_given(
        "Build model.js and wire it into app.js", [_order("app/app.js")], tmp_path, "app"
    )

    assert unassigned == ["model.js"]
