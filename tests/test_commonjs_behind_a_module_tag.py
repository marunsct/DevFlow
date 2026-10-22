"""CommonJS behind `<script type="module">`, which no browser can run.

One run shipped `index.html` carrying

    <script type="module" src="app.js"></script>

against an `app.js` ending in `module.exports = { loadTasks, ... }`. `module`
does not exist in a browser under any script type, so the page throws
`Uncaught ReferenceError: module is not defined` and nothing on it works.

Neither half is wrong on its own, which is why every gate passed it: Node's
test runner loads the same file as CommonJS, where those exports are exactly
right, and its ESM interop even synthesises named imports from them. The
product is dead only in the one place a user opens it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import _commonjs_loaded_as_a_module

MODULE_TAG = '<!DOCTYPE html>\n<script type="module" src="app.js"></script>\n'
PLAIN_TAG = '<!DOCTYPE html>\n<script src="app.js"></script>\n'
COMMONJS = "function init() {}\nmodule.exports = { init };\n"
ESM = "export function init() {}\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "todo"
    directory.mkdir()
    return directory


def _problems(project: Path) -> list[str]:
    return _commonjs_loaded_as_a_module([project / "index.html"], project.parent)


def test_commonjs_behind_a_module_tag_is_reported(project: Path):
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")
    (project / "app.js").write_text(COMMONJS, encoding="utf-8")

    problems = _problems(project)

    assert len(problems) == 1
    assert "module is not defined" in problems[0]
    assert "app.js" in problems[0]


def test_the_note_says_the_test_suite_cannot_catch_it(project: Path):
    """Because `node --test` loads the same file as CommonJS, correctly."""
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")
    (project / "app.js").write_text(COMMONJS, encoding="utf-8")

    assert "test suite cannot catch this" in _problems(project)[0]


def test_a_real_module_behind_a_module_tag_is_left_alone(project: Path):
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")
    (project / "app.js").write_text(ESM, encoding="utf-8")

    assert _problems(project) == []


def test_commonjs_behind_a_plain_tag_is_not_this_check(project: Path):
    """A classic script tag is the shape Node and the browser both tolerate."""
    (project / "index.html").write_text(PLAIN_TAG, encoding="utf-8")
    (project / "app.js").write_text(COMMONJS, encoding="utf-8")

    assert _problems(project) == []


def test_a_file_using_both_module_systems_is_left_alone(project: Path):
    """Mixing them is a different mistake, and a bundler may be resolving it."""
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")
    (project / "app.js").write_text(ESM + COMMONJS, encoding="utf-8")

    assert _problems(project) == []


def test_a_require_call_counts_as_commonjs(project: Path):
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")
    (project / "app.js").write_text("const fs = require('fs');\n", encoding="utf-8")

    assert len(_problems(project)) == 1


def test_a_missing_script_target_is_not_reported(project: Path):
    (project / "index.html").write_text(MODULE_TAG, encoding="utf-8")

    assert _problems(project) == []
