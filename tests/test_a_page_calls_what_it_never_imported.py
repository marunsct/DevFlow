"""A module script calling a name its own module exports but never imports.

An inline `<script type="module">` is a module. An identifier it neither
imports nor declares is not a global lookup that might work: it is a
`ReferenceError` on the line that reaches it.

Found on one run of 2026-09-20, against `tests/brief_low.md`. The page
imported six names from `./app-logic.mjs` and then called five different ones -
`addTaskAndPersist`, `toggleTaskAndPersist`, `deleteTaskAndPersist`,
`loadPersistedTasks` and `getFilteredTasksFromState` - every one of them an
export of that same module, none of them in the clause. Four of the six it did
import were never used. `init()` calls `loadPersistedTasks()` on
`DOMContentLoaded`, so the page threw on load and no control in it ever worked.

The suite could not see it: it reaches `app-logic.mjs` directly through
`import * as appLogic`, so every pure function passed, and that run wrote no
browser test at all. The page is the only place the wiring exists.

Both reviewers did catch this one - the security review graded it `critical`
and the milestone review `Blocking`, with the corrected import clause written
out in full. The check earns its place by being deterministic rather than by
being the only thing that looks: it fires when the file is written instead of
at the end of a sprint, and a reviewer is a model, which is how one run's
missing viewport tag passed a security review and five milestone reviews.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _called_without_being_imported,
    _source_files,
)

MODULE = """
export function addTask(title) { return { title }; }
export function addTaskAndPersist(title, storage) { storage.setItem('t', title); }
export function loadPersistedTasks(storage) { return storage.getItem('t'); }
export function setRenderCallback(fn) { return fn; }
"""


def _problems(root):
    return _called_without_being_imported(_source_files(root), root)


def _page(body: str) -> str:
    return (
        "<!doctype html><html><head><title>t</title></head><body>\n"
        '<script type="module">\n' + body + "\n</script>\n"
        "</body></html>\n"
    )


@pytest.fixture
def site(tmp_path):
    (tmp_path / "app-logic.mjs").write_text(MODULE)
    return tmp_path


def test_the_exact_page_that_shipped_broken(site):
    """One run's shape: imports one set of names, calls another."""
    (site / "index.html").write_text(_page("""
    import { addTask, setRenderCallback } from './app-logic.mjs';

    function init() {
      loadPersistedTasks();
    }
    document.addEventListener('DOMContentLoaded', init);
    form.addEventListener('submit', () => addTaskAndPersist('x'));
    """))

    problems = _problems(site)
    assert len(problems) == 1
    reported = problems[0]
    assert "addTaskAndPersist" in reported
    assert "loadPersistedTasks" in reported
    # The name the *first* failure raises, so the message matches the console.
    # `loadPersistedTasks()` is called from `init`, which is written above the
    # submit handler, so it is the one the browser reaches first - not the
    # alphabetically first, which is what an earlier version reported.
    assert "ReferenceError: loadPersistedTasks is not defined" in reported
    # It must point at the fix, which is already on disk.
    assert "app-logic.mjs" in reported


def test_a_page_that_imports_what_it_calls_is_silent(site):
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist, loadPersistedTasks } from './app-logic.mjs';

    loadPersistedTasks();
    addTaskAndPersist('x');
    """))
    assert _problems(site) == []


def test_a_renamed_import_still_counts_as_bound(site):
    """`as` binds the name on the right, and that is the one being called."""
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist as add } from './app-logic.mjs';
    add('x');
    """))
    assert _problems(site) == []


def test_a_namespace_import_is_not_reported(site):
    """`appLogic.addTaskAndPersist(...)` is a member call, never a bare name."""
    (site / "index.html").write_text(_page("""
    import * as appLogic from './app-logic.mjs';
    appLogic.addTaskAndPersist('x');
    """))
    assert _problems(site) == []


def test_a_name_the_module_does_not_export_is_left_alone(site):
    """The narrowness that keeps this check honest.

    A bare call to something the module has no export for may be a browser
    global, a name from another script, or a genuine mistake this check cannot
    tell apart. Only the case whose fix is already on disk is reported.
    """
    (site / "index.html").write_text(_page("""
    import { addTask } from './app-logic.mjs';
    fetch('/x');
    structuredClone({});
    requestAnimationFrame(() => addTask('y'));
    """))
    assert _problems(site) == []


def test_a_locally_declared_function_is_bound(site):
    """Shadowing an export is legal; the page defines its own and calls that."""
    (site / "index.html").write_text(_page("""
    import { addTask } from './app-logic.mjs';
    function loadPersistedTasks() { return []; }
    const setRenderCallback = (fn) => fn;
    loadPersistedTasks();
    setRenderCallback(() => addTask('x'));
    """))
    assert _problems(site) == []


def test_a_call_inside_a_comment_is_not_a_call(site):
    (site / "index.html").write_text(_page("""
    import { addTask } from './app-logic.mjs';
    // loadPersistedTasks();
    /* addTaskAndPersist('x'); */
    addTask('x');
    """))
    assert _problems(site) == []


def test_a_page_with_no_relative_import_is_silent(site):
    """Nothing to compare against, so nothing can be said."""
    (site / "index.html").write_text(_page("""
    loadPersistedTasks();
    """))
    assert _problems(site) == []


def test_a_missing_module_file_is_not_guessed_at(site):
    (site / "index.html").write_text(_page("""
    import { addTask } from './not-written-yet.mjs';
    loadPersistedTasks();
    """))
    assert _problems(site) == []


def test_keywords_that_take_a_parenthesis_are_not_calls(site):
    """`if (`, `for (`, `catch (` and friends must not read as bare calls."""
    (site / "index.html").write_text(_page("""
    import { addTask } from './app-logic.mjs';
    if (true) { for (let i = 0; i < 1; i++) { try { addTask('x'); } catch (e) {} } }
    switch (1) { case 1: break; }
    """))
    assert _problems(site) == []


def test_the_line_it_names_is_the_line_that_throws(site):
    """The message points at a line a reader can open, not a guess.

    Execution order is not knowable from the text, and alphabetical order is
    not execution order. What *is* knowable is where in the file the first of
    these calls is written, so that is what the message reports.
    """
    (site / "index.html").write_text(
        "<!doctype html>\n"          # line 1
        "<html><body>\n"             # line 2
        '<script type="module">\n'   # line 3
        "import { addTask } from './app-logic.mjs';\n"   # line 4
        "setRenderCallback(() => {});\n"                 # line 5  <- first
        "loadPersistedTasks();\n"                        # line 6
        "</script>\n</body></html>\n"
    )

    reported = _problems(site)[0]
    assert "line 5 throws `ReferenceError: setRenderCallback is not defined`" in reported
