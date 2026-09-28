"""A test that calls a local function with more arguments than it takes.

JavaScript drops the extra ones in silence. One run wrote

    addTask(storage, 'Active Task', '', false)

against `addTask({ title, description = '' }, storage)`: every argument
landed one place left, and the run's only discoverable suite died three times
on `storage.setItem is not a function`. One run is the quiet version -
`addTask('Completed Task 1', '', true)` against `addTask(title, description)`,
where the `true` was dropped and the assertions about completed tasks ran
against tasks nothing had completed.

Three of the 248 stored workspace scripts trip it and all three are real.
"""

from __future__ import annotations

from app.analysis.test_discovery import a_call_the_signature_does_not_accept


def _project(tmp_path, module: str, suite: str, module_name: str = "app.js"):
    (tmp_path / module_name).write_text(module)
    (tmp_path / "app.test.mjs").write_text(suite)
    return a_call_the_signature_does_not_accept("app.test.mjs", suite, tmp_path)


def test_the_call_that_shifted_every_argument_one_place(tmp_path):
    note = _project(
        tmp_path,
        "export function addTask({ title, description = '' }, storage) {}\n",
        "import { addTask } from './app.js';\n"
        "addTask(storage, 'Active Task', '', false);\n",
    )
    assert note is not None
    assert "4 arguments" in note and "takes 2" in note


def test_the_dropped_argument_that_never_throws(tmp_path):
    note = _project(
        tmp_path,
        "function addTask(title, description) {}\nexport { addTask };\n",
        "import { addTask } from './app.js';\n"
        "addTask('Completed Task 1', '', true);\n",
    )
    assert note is not None and "takes 2" in note


def test_a_call_that_matches_the_signature_is_silent(tmp_path):
    assert (
        _project(
            tmp_path,
            "export function addTask(title, description) {}\n",
            "import { addTask } from './app.js';\naddTask('a', 'b');\n",
        )
        is None
    )


def test_passing_fewer_than_declared_is_silent(tmp_path):
    """Omitting a trailing argument is ordinary JavaScript, not a mistake."""
    assert (
        _project(
            tmp_path,
            "export function addTask(title, description, storage) {}\n",
            "import { addTask } from './app.js';\naddTask('a');\n",
        )
        is None
    )


def test_a_rest_parameter_accepts_anything(tmp_path):
    assert (
        _project(
            tmp_path,
            "export function log(prefix, ...rest) {}\n",
            "import { log } from './app.js';\nlog('a', 1, 2, 3, 4);\n",
        )
        is None
    )


def test_an_arrow_function_is_read_the_same_way(tmp_path):
    note = _project(
        tmp_path,
        "export const addTask = (title, description) => {};\n",
        "import { addTask } from './app.js';\naddTask('a', 'b', true);\n",
    )
    assert note is not None


def test_a_require_of_a_local_module_is_read_the_same_way(tmp_path):
    note = _project(
        tmp_path,
        "function addTask(title, description) {}\nmodule.exports = { addTask };\n",
        "const { addTask } = require('./app.js');\naddTask('a', 'b', true);\n",
    )
    assert note is not None


def test_a_package_import_is_not_resolved(tmp_path):
    """Only local modules - a signature this cannot read it says nothing about."""
    assert (
        _project(
            tmp_path,
            "export function addTask(title) {}\n",
            "import { JSDOM } from 'jsdom';\nnew JSDOM('a', 'b', 'c');\n",
        )
        is None
    )


def test_a_method_call_of_the_same_name_is_not_the_import(tmp_path):
    """`list.addTask(a, b, c)` is some other object's method."""
    assert (
        _project(
            tmp_path,
            "export function addTask(title, description) {}\n",
            "import { addTask } from './app.js';\n"
            "manager.addTask('a', 'b', 'c');\n",
        )
        is None
    )


def test_an_argument_holding_a_comma_counts_once(tmp_path):
    """An object literal or a nested call is one argument, not several."""
    assert (
        _project(
            tmp_path,
            "export function addTask(task, storage) {}\n",
            "import { addTask } from './app.js';\n"
            "addTask({ title: 'a', description: 'b' }, makeStore(1, 2));\n",
        )
        is None
    )


def test_a_comma_inside_a_string_is_not_a_separator(tmp_path):
    assert (
        _project(
            tmp_path,
            "export function addTask(title, description) {}\n",
            "import { addTask } from './app.js';\naddTask('a, b, c', 'd');\n",
        )
        is None
    )


def test_a_file_that_is_not_a_test_is_left_alone(tmp_path):
    (tmp_path / "app.js").write_text("export function addTask(title) {}\n")
    suite = "import { addTask } from './app.js';\naddTask('a', 'b');\n"
    assert a_call_the_signature_does_not_accept("main.js", suite, tmp_path) is None


def test_no_directory_means_no_signature_to_read(tmp_path):
    suite = "import { addTask } from './app.js';\naddTask('a', 'b', 'c');\n"
    assert a_call_the_signature_does_not_accept("app.test.mjs", suite, None) is None


def test_a_module_that_is_not_on_disk_is_not_guessed_at(tmp_path):
    suite = "import { addTask } from './missing.js';\naddTask('a', 'b', 'c');\n"
    (tmp_path / "app.test.mjs").write_text(suite)
    assert (
        a_call_the_signature_does_not_accept("app.test.mjs", suite, tmp_path) is None
    )
