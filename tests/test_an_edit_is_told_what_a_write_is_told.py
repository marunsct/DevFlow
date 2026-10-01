"""An edit is told what a write of the same file would be told.

The write path ran three module-system notes the edit path did not: CommonJS
in a `.js` file under `"type": "module"`, a manifest whose `"type"` breaks the
files beside it, and a page that loads a module the wrong way. One run's
`defect_fix_1_2` used `replace_lines` to turn a test's `import` lines into
`require(...)` under `"type": "module"`, was told nothing, and the next test
round reported "require is not defined".
"""

from __future__ import annotations

import inspect
import json

from app.tools import repository
from app.tools.repository import edit_approved_artifact, replace_approved_lines

TEST = "import { test } from 'node:test';\nimport assert from 'node:assert';\n\ntest('x', () => assert.ok(true));\n"


def _package(tmp_path):
    project = tmp_path / "app"
    (project / "tests").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({"name": "app", "type": "module"}), encoding="utf-8")
    (project / "tests" / "a.test.js").write_text(TEST, encoding="utf-8")
    return project


def test_replace_lines_says_require_will_not_run_here(tmp_path) -> None:
    _package(tmp_path)

    result = replace_approved_lines(
        tmp_path, "app/tests/a.test.js", 1, 2,
        "const { test } = require('node:test');\nconst assert = require('node:assert');",
    )

    assert "require is not defined in ES module scope" in result.get("note", "")


def test_edit_artifact_says_it_too(tmp_path) -> None:
    _package(tmp_path)

    result = edit_approved_artifact(
        tmp_path, "app/tests/a.test.js",
        "import assert from 'node:assert';", "const assert = require('node:assert');",
    )

    assert "require is not defined in ES module scope" in result.get("note", "")


def test_an_edit_in_the_module_s_own_syntax_says_nothing_of_it(tmp_path) -> None:
    _package(tmp_path)

    result = replace_approved_lines(
        tmp_path, "app/tests/a.test.js", 2, 2, "import { strict as assert } from 'node:assert';"
    )

    assert "require is not defined" not in result.get("note", "")


def test_every_module_system_note_on_the_write_path_is_on_the_edit_path() -> None:
    """The twelve-of-thirteen shape: a check on one path and not its twin."""
    edit_path = inspect.getsource(repository._edited)
    for note in (
        "_the_module_type_this_declares_breaks_files_here",
        "_the_module_type_here_rejects_this_file",
        "_the_page_and_this_module_disagree_on_how_it_loads",
    ):
        assert note in edit_path, note
