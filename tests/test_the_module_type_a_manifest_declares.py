"""A manifest whose `"type"` contradicts the `.js` files beside it.

One line of one file decides how Node parses every `.js` in the directory, and
the stage that writes it is rarely the stage that wrote them. Run 9bd3a091's
`specialist_testing_3`, reaching for jest to escape a failing assertion,
rewrote `"type": "module"` to `"type": "commonjs"` while every export in
`app.js` was still ES syntax. The write went through in silence; `node --check
app.js` then gave `SyntaxError: Unexpected token 'export'` and nothing in the
product loaded under Node again.

Seven of the fifty-one stored workspaces end the other way round - `"type":
"module"` over a file still calling `require` - which is 8 of 56 manifests
once run 9bd3a091 is counted.

A note and not a refusal: flipping the type is the legitimate first step of a
conversion, and refusing it would leave no order in which the work could be
done.
"""

from __future__ import annotations

import json

from app.tools.repository import write_approved_artifact


def _note(tmp_path, manifest: dict, **files: str) -> str:
    project = tmp_path / "proj"
    project.mkdir(exist_ok=True)
    for name, body in files.items():
        (project / name.replace("__", ".")).write_text(body)
    written = write_approved_artifact(tmp_path, "proj/package.json", json.dumps(manifest))
    return written.get("note", "")


def test_flipping_to_commonjs_under_es_modules_is_named(tmp_path):
    note = _note(tmp_path, {"type": "commonjs"}, app__js="export function addTask(t) {}\n")
    assert "app.js" in note and '"type": "commonjs"' in note
    assert "ES module syntax" in note


def test_declaring_module_over_a_require_is_named(tmp_path):
    note = _note(
        tmp_path,
        {"type": "module"},
        app__js="const fs = require('fs');\nmodule.exports = {};\n",
    )
    assert "app.js" in note and "CommonJS syntax" in note


def test_a_tool_config_is_the_common_case(tmp_path):
    """Run 3c0c31d2 left `babel.config.js` and `jest.config.js` on
    `module.exports` under `"type": "module"`, where each throws
    `ReferenceError: module is not defined in ES module scope`.
    """
    note = _note(
        tmp_path,
        {"type": "module"},
        jest__config__js="module.exports = { testMatch: ['**/*.mjs'] };\n",
    )
    assert "jest.config.js" in note


def test_a_consistent_manifest_says_nothing(tmp_path):
    assert _note(tmp_path, {"type": "module"}, app__js="export function a() {}\n") == ""


def test_a_consistent_commonjs_manifest_says_nothing(tmp_path):
    assert _note(tmp_path, {"type": "commonjs"}, app__js="module.exports = {};\n") == ""


def test_a_manifest_that_declares_no_type_says_nothing(tmp_path):
    assert _note(tmp_path, {"name": "p"}, app__js="export function a() {}\n") == ""


def test_a_file_using_both_is_not_called_contradicting(tmp_path):
    """Mixed syntax is its own problem and another check's; this one only
    speaks when a file is wholly on the other side."""
    assert (
        _note(
            tmp_path,
            {"type": "commonjs"},
            app__js="import x from 'y';\nmodule.exports = {};\n",
        )
        == ""
    )


def test_a_require_inside_a_comment_is_not_a_require(tmp_path):
    assert (
        _note(
            tmp_path,
            {"type": "module"},
            app__js="// const x = require('y');\nexport function a() {}\n",
        )
        == ""
    )


def test_explicit_extensions_are_exempt_from_the_declared_type(tmp_path):
    """`.mjs` is always a module and `.cjs` always CommonJS, whatever the
    manifest says - only `.js` is decided by the `type` field."""
    assert (
        _note(
            tmp_path,
            {"type": "commonjs"},
            a__mjs="export function a() {}\n",
            b__cjs="module.exports = {};\n",
        )
        == ""
    )


def test_it_says_what_to_do_about_it(tmp_path):
    note = _note(tmp_path, {"type": "commonjs"}, app__js="export function a() {}\n")
    assert "Convert it in this sprint or leave the `type` as it was" in note
    assert "one choice for the whole directory" in note


def test_some_other_json_file_is_not_a_manifest(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.js").write_text("export function a() {}\n")
    written = write_approved_artifact(
        tmp_path, "proj/tsconfig.json", json.dumps({"type": "commonjs"})
    )
    assert "type" not in written.get("note", "")


def test_the_note_agrees_with_itself_on_number(tmp_path):
    """One file reads as one file, several as several.

    It said "that file ... no longer load" until a probe of both numbers
    caught it, which is the sort of thing a reader stops trusting a note over.
    """
    one = _note(tmp_path, {"type": "commonjs"}, app__js="export function a() {}\n")
    assert "that file no longer loads" in one and "Convert it" in one

    two = _note(
        tmp_path,
        {"type": "commonjs"},
        app__js="export function a() {}\n",
        b__js="export function b() {}\n",
    )
    assert "those files no longer load" in two and "Convert them" in two
