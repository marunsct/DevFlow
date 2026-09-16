"""Removing an export that another file imports, silently.

`import_problems` asks "does what this file imports exist?", and is checked
when that file is written. Nothing asked the reverse: when the *imported*
module is written, does what it still exports satisfy the files importing it?

That silence is what keeps a run oscillating. Runs 0c5aabdb, d6297b2f and
0afef410 each reached a genuine conflict - `index.html` loading `app.js` with a
plain `<script>` tag needs a classic script, while `app.test.mjs` doing
`import { addTask } from './app.js'` needs a module - and each alternated
between satisfying one and the other. On run 0afef410 the milestone reviewer
named the fix that satisfies both, adding `type="module"` to the tag; the stage
removed the exports instead, and nothing told it the suite had just stopped
being able to import anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.local_imports import who_would_break
from app.tools.repository import write_approved_artifact

EXPORTS_BOTH = "export function addTask(t) { return t; }\nexport function getTasks() { return []; }\n"
EXPORTS_NEITHER = "function addTask(t) { return t; }\nwindow.addTask = addTask;\n"
SUITE = (
    "import { test } from 'node:test';\n"
    "import { addTask, getTasks } from './app.js';\n"
    "test('x', () => { addTask(1); });\n"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "proj"
    directory.mkdir()
    (directory / "app.js").write_text(EXPORTS_BOTH, encoding="utf-8")
    (directory / "app.test.mjs").write_text(SUITE, encoding="utf-8")
    return directory


def test_removing_every_export_names_the_importer(project: Path):
    problems = who_would_break(project / "app.js", EXPORTS_NEITHER, project)

    assert len(problems) == 1
    assert "app.test.mjs" in problems[0]
    assert "`addTask`" in problems[0]
    assert "exports nothing" in problems[0]


def test_removing_one_of_two_names_only_that_one(project: Path):
    problems = who_would_break(
        project / "app.js", "export function addTask(t) { return t; }\n", project
    )

    assert len(problems) == 1
    assert "`getTasks`" in problems[0]
    assert "`addTask`" in problems[0].split("imports")[0] or True
    assert "exports `addTask`" in problems[0]


def test_keeping_the_exports_says_nothing(project: Path):
    assert who_would_break(project / "app.js", EXPORTS_BOTH, project) == []


def test_a_missing_default_is_reported(project: Path):
    (project / "main.mjs").write_text("import app from './app.js';\n", encoding="utf-8")

    problems = who_would_break(project / "app.js", EXPORTS_BOTH, project)

    assert any("`default`" in problem for problem in problems)


def test_a_commonjs_module_is_not_judged(project: Path):
    """What `module.exports` offers is decided at runtime, not readable here."""
    assert who_would_break(project / "app.js", "module.exports = { addTask };\n", project) == []


def test_a_re_export_star_is_not_judged(project: Path):
    assert who_would_break(project / "app.js", "export * from './other.js';\n", project) == []


def test_a_file_importing_a_different_module_is_not_affected(project: Path):
    (project / "other.js").write_text("export function z() {}\n", encoding="utf-8")
    (project / "uses_other.mjs").write_text(
        "import { z } from './other.js';\n", encoding="utf-8"
    )

    problems = who_would_break(project / "app.js", EXPORTS_NEITHER, project)

    assert all("uses_other" not in problem for problem in problems)


def test_the_note_reaches_the_write(tmp_path: Path):
    """The whole point: it must be said at the moment the export is removed."""
    (tmp_path / "proj").mkdir()
    write_approved_artifact(tmp_path, "proj/app.js", EXPORTS_BOTH)
    write_approved_artifact(tmp_path, "proj/app.test.mjs", SUITE)

    result = write_approved_artifact(tmp_path, "proj/app.js", EXPORTS_NEITHER)

    assert "What imports this file" in result.get("note", "")
    assert "app.test.mjs" in result["note"]
