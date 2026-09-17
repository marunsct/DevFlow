"""`node --check foo.js` is not the parser that loads `foo.js`.

`--check` parses with the script goal. A typeless `.js` holding `export` is
*loaded* with the module goal - detect-module has been on since Node 20.19 -
and the module goal has early errors the script goal has no equivalent for: a
duplicate export, an export of a name the module never defines. So `--check`
passes files Node then refuses to load, which is exactly what the check exists
to prevent.

Measured over every `.js` write in the stored transcripts that uses ES module
syntax: **17 of 116** pass `node --check` and throw on import. Four runs paid
for it - d6297b2f twice on `Duplicate export of 'init'`, f81808a4 on
`Export 'addTask' is not defined in module`, 551640d3 fourteen times, and run
1cd4597b spent 177 events of a defect-fix stage on `Duplicate export of
'deleteHandler'`.

Verified by loading the files rather than by reading Node's flags: each one
sampled passes `--check` and raises `SyntaxError` on a real `import()`.
"""

from __future__ import annotations

import json

import pytest

from app.analysis.javascript_parse import parse_error

A_DUPLICATE_EXPORT = (
    "export function init() {}\nfunction other() {}\nexport { other, init };\n"
)
AN_UNDEFINED_EXPORT = "function addTask(t) { return t; }\nexport { addTask, missingOne };\n"
A_GOOD_MODULE = "export function addTask(t) { return t; }\nexport function render() {}\n"


@pytest.mark.parametrize(
    "name", ["script.js", "script.mjs"]
)
def test_a_duplicate_export_is_reported(tmp_path, name):
    """`.mjs` was already caught; `.js` is the one that was not."""
    found = parse_error(tmp_path / name, A_DUPLICATE_EXPORT)
    assert found is not None
    assert "Duplicate export of 'init'" in found


def test_exporting_a_name_the_module_does_not_define_is_reported(tmp_path):
    found = parse_error(tmp_path / "script.js", AN_UNDEFINED_EXPORT)
    assert found is not None and "missingOne" in found


def test_the_stray_semicolon_from_run_551640d3(tmp_path):
    """An object literal with `setTasks: (tasks) => {};` inside it."""
    found = parse_error(
        tmp_path / "script.js",
        "export const store = {\n  getItem: () => null,\n"
        "  setTasks: (tasks) => {};\n};\n",
    )
    assert found is not None


@pytest.mark.parametrize(
    "content",
    [
        A_GOOD_MODULE,
        "const fs = require('fs');\nmodule.exports = { fs };\n",
        "function addTask(t) { return t; }\nwindow.addTask = addTask;\n",
        "import { test } from 'node:test';\ntest('x', () => {});\n",
    ],
)
def test_a_file_node_can_load_is_not_reported(tmp_path, content):
    assert parse_error(tmp_path / "script.js", content) is None


def test_a_real_brace_error_is_still_reported(tmp_path):
    """The script-goal check must keep working; this is additive."""
    assert parse_error(tmp_path / "script.js", "export function a() {\n") is not None


def test_es_syntax_under_type_commonjs_is_reported_by_the_script_goal(tmp_path):
    """Not by the module goal - the manifest pins it to CommonJS, where
    `export` cannot parse at all, and that is the error worth reporting."""
    (tmp_path / "package.json").write_text(json.dumps({"type": "commonjs"}))
    found = parse_error(tmp_path / "script.js", A_DUPLICATE_EXPORT)
    assert found is not None
    assert "Unexpected token 'export'" in found


def test_a_correct_module_under_type_module_is_silent(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
    assert parse_error(tmp_path / "script.js", A_GOOD_MODULE) is None


def test_a_commonjs_file_under_type_commonjs_is_silent(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"type": "commonjs"}))
    assert parse_error(tmp_path / "script.js", "module.exports = { a: 1 };\n") is None


def test_the_second_parse_only_runs_for_js_using_module_syntax(tmp_path):
    """It costs a second `node` invocation, so it must not run on every write.

    `.cjs` is never a module and a file with no `export`/`import` cannot hit a
    module-goal early error, so neither reaches the second parse.
    """
    from app.analysis.javascript_parse import _the_module_goal_also_rejects

    assert _the_module_goal_also_rejects("node", tmp_path / "a.cjs", A_DUPLICATE_EXPORT) is None
    assert _the_module_goal_also_rejects("node", tmp_path / "a.mjs", A_DUPLICATE_EXPORT) is None
    assert _the_module_goal_also_rejects("node", tmp_path / "a.js", "const x = 1;\n") is None


def test_an_edit_that_breaks_a_module_is_refused_not_merely_noted(tmp_path):
    """The behaviour change this introduced, pinned deliberately.

    Before, an edit leaving `export function init() {` with an unclosed brace
    passed `node --check` as a script and got a brace-counting note. It now
    fails the module-goal parse and is refused, which is what
    `_refuses_a_broken_file` does everywhere else - the file cannot load, and
    a note that leaves it on disk broken is the weaker answer.
    """
    from app.tools.repository import (
        RepositoryToolError,
        edit_approved_artifact,
        write_approved_artifact,
    )

    write_approved_artifact(
        tmp_path, "p/app.js", "export function init() {\n  const f = 1;\n}\n"
    )
    with pytest.raises(RepositoryToolError) as refusal:
        edit_approved_artifact(tmp_path, "p/app.js", "    const f = 1;\n", "  if (x) {\n")
    assert "Nothing was changed" in str(refusal.value)
