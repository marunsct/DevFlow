"""A suite that defines the application's own function and tests its copy.

The assertions are real, the logic is real, and none of it is connected to the
product: the suite passes whatever the application does, and every gate
downstream reads the pass.

`_redefined_instead_of_imported` finds it at a milestone review. Run 1cd4597b
is why that is not enough - `crud.test.mjs` and `filter.test.mjs` each defined
their own `loadTasks` beside an import of the module that exports it, the
finding was reported at the end of two consecutive sprints, and both files
still carried it at the end of the third. Five more workspaces end this way,
run 1ae7671d with eight files.

Unlike the findings 4t says cannot move earlier, the evidence is all present
at the write: the suite names a relative module, so that module is on disk.
"""

from __future__ import annotations

import pytest

from app.analysis.test_discovery import a_name_this_test_defines_instead_of_importing

A_MODULE = (
    "export function loadTasks() { return JSON.parse(localStorage.getItem('t') || '[]'); }\n"
    "export function createTask(title) { return { id: 1, title }; }\n"
)


def _note(tmp_path, suite: str, name: str = "crud.test.mjs", module=A_MODULE):
    (tmp_path / "script.js").write_text(module)
    return a_name_this_test_defines_instead_of_importing(name, suite, tmp_path)


def test_the_run_1cd4597b_shape_is_named(tmp_path):
    """Its own `loadTasks` beside a real import of the same module."""
    note = _note(
        tmp_path,
        "import { createTask } from './script.js';\n"
        "function loadTasks() { return []; }\n"
        "test('x', () => {});\n",
    )
    assert note is not None
    assert "loadTasks" in note and "script.js" in note
    assert "pass whatever" in note
    # The import makes it more confusing, not less, and the note says so.
    assert "shadowing" in note or "leaves the assertions pointing at the copy" in note


def test_a_copy_with_no_import_at_all_is_named(tmp_path):
    note = _note(tmp_path, "function loadTasks() { return []; }\ntest('x', () => {});\n")
    assert note is not None and "Import loadTasks from `./script.js`" in note


def test_a_const_arrow_copy_is_named(tmp_path):
    note = _note(
        tmp_path,
        "import { createTask } from './script.js';\nconst loadTasks = () => [];\n",
    )
    assert note is not None


def test_importing_the_name_properly_is_silent(tmp_path):
    assert _note(tmp_path, "import { loadTasks, createTask } from './script.js';\n") is None


def test_a_helper_the_module_does_not_export_is_silent(tmp_path):
    """Test fixtures are not copies; only a name the application also has."""
    assert (
        _note(
            tmp_path,
            "import { loadTasks } from './script.js';\n"
            "function makeFixture() { return [{ id: 1 }]; }\n",
        )
        is None
    )


def test_a_file_that_is_not_a_test_is_left_alone(tmp_path):
    assert _note(tmp_path, "function loadTasks() { return []; }\n", name="helpers.js") is None


def test_no_directory_means_nothing_to_compare_against(tmp_path):
    assert (
        a_name_this_test_defines_instead_of_importing(
            "a.test.mjs", "function loadTasks() { return []; }\n", None
        )
        is None
    )


def test_the_module_is_found_from_a_subdirectory(tmp_path):
    """`src/manual_regression.test.js` and `tests/tasks.test.js` both sit a
    level below the file they copy from; looking only beside the suite missed
    both, and the two readings then disagreed."""
    (tmp_path / "script.js").write_text(A_MODULE)
    nested = tmp_path / "tests"
    nested.mkdir()
    assert (
        a_name_this_test_defines_instead_of_importing(
            "tasks.test.js", "function loadTasks() { return []; }\n", nested
        )
        is not None
    )


def test_the_two_readings_of_a_redefined_name_agree(tmp_path):
    """The write-time note and the cross-file check must not drift.

    They share their patterns by import rather than by copy; this pins the
    behaviour, in both directions.
    """
    from app.analysis.integration_checks import _redefined_instead_of_imported

    project = tmp_path / "proj"
    project.mkdir()
    (project / "script.js").write_text(A_MODULE)
    suite = project / "crud.test.mjs"
    copy = "import { createTask } from './script.js';\nfunction loadTasks() { return []; }\n"
    suite.write_text(copy)

    assert bool(_redefined_instead_of_imported([suite, project / "script.js"], project)) == bool(
        a_name_this_test_defines_instead_of_importing("crud.test.mjs", copy, project)
    )

    proper = "import { loadTasks, createTask } from './script.js';\n"
    suite.write_text(proper)
    assert not _redefined_instead_of_imported([suite, project / "script.js"], project)
    assert (
        a_name_this_test_defines_instead_of_importing("crud.test.mjs", proper, project)
        is None
    )
