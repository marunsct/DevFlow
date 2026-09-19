"""A source file that contradicts the manifest beside it must say so at the write.

`_the_module_type_this_declares_breaks_files_here` checks a *manifest* against
the files around it. Nothing checked a *file* against the manifest already
there, so one contradiction was caught from one side and invisible from the
other - the twelve-of-thirteen shape this codebase keeps meeting.

Only the CommonJS-into-ESM direction needs saying here. ESM into CommonJS is a
parse error and `node --check` refuses it at the write already; `require` in
an ES module is perfectly good syntax and fails only when it runs, so no
parser sees it and the cost lands on whoever runs the file.

Measured live on run-eb48de7a. `specialist_testing_5` wrote
`todo-app/test_core.js` opening `const assert = require('assert');` into a
project whose `package.json` says `"type": "module"`. The write was accepted
in silence. The next call ran it and got `ReferenceError: require is not
defined in ES module scope`; the stage then tried to delete the file (refused,
it is a test), to write a `.cjs` twin (refused, a second copy of the module),
read both files and the manifest, and finally rewrote it as ESM. Fourteen
model calls to learn something both facts needed for were on disk at the
moment of the write.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.tools.repository import (
    _the_module_type_here_rejects_this_file,
    write_approved_artifact,
)

MARKER = "require is not defined in ES module scope"


@pytest.fixture()
def esm_project(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "app").mkdir()
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    (tmp_path / "app" / "package.json").write_text(
        json.dumps({"name": "a", "version": "1.0.0", "type": "module"}), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    "content",
    [
        "const assert = require('assert');\n",
        "const { a, b } = require('./main.js');\n",
        "module.exports = { a: 1 };\n",
        "exports.run = function () {};\n",
        "var fs = require('fs');\n",
    ],
)
def test_commonjs_written_into_an_esm_project_is_flagged(esm_project, content):
    result = write_approved_artifact(esm_project, "app/x.js", content)
    assert MARKER in (result.get("note") or ""), content


@pytest.mark.parametrize(
    "content",
    [
        "import assert from 'assert';\n",
        "export function f() { return 1; }\n",
        "// this file is about require() and module.exports\n",
        "const text = \"use require('x') in CommonJS\";\n",
    ],
)
def test_es_module_content_and_mere_mentions_are_not_flagged(esm_project, content):
    result = write_approved_artifact(esm_project, "app/y.js", content)
    assert MARKER not in (result.get("note") or ""), content


def test_a_cjs_file_carries_its_own_answer(esm_project):
    """`.cjs` is CommonJS whatever the manifest says, so there is nothing to warn about."""
    result = write_approved_artifact(esm_project, "app/legacy.cjs", "const a = require('assert');\n")
    assert MARKER not in (result.get("note") or "")


def test_a_project_with_no_type_is_not_flagged(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    (tmp_path / "app" / "package.json").write_text(
        json.dumps({"name": "a"}), encoding="utf-8"
    )
    result = write_approved_artifact(tmp_path, "app/x.js", "const a = require('assert');\n")
    assert MARKER not in (result.get("note") or "")


def test_a_project_with_no_manifest_is_not_flagged(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    result = write_approved_artifact(tmp_path, "app/x.js", "const a = require('assert');\n")
    assert MARKER not in (result.get("note") or "")


def test_the_note_names_the_two_ways_out(esm_project):
    note = _the_module_type_here_rejects_this_file(
        esm_project / "app" / "x.js", "const a = require('assert');\n"
    )
    assert "import" in note and "move_artifact" in note, (
        "a correction must name the fix, and there are exactly two here"
    )


def test_it_is_a_note_and_not_a_refusal(esm_project):
    """A file about to be renamed to `.cjs` is a legitimate intermediate state."""
    result = write_approved_artifact(esm_project, "app/x.js", "const a = require('assert');\n")
    assert result.get("status") == "written"
    assert (esm_project / "app" / "x.js").is_file()


def test_both_directions_of_the_contradiction_now_have_a_check():
    """The set rule: manifest-against-files and file-against-manifest."""
    from app.tools import repository

    assert hasattr(repository, "_the_module_type_this_declares_breaks_files_here")
    assert hasattr(repository, "_the_module_type_here_rejects_this_file")
