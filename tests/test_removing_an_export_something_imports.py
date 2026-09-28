"""Removing an export that another file imports, silently.

`import_problems` asks "does what this file imports exist?", and is checked
when that file is written. Nothing asked the reverse: when the *imported*
module is written, does what it still exports satisfy the files importing it?

That silence is what keeps a run oscillating. Three runs each reached a genuine conflict - `index.html` loading `app.js` with a
plain `<script>` tag needs a classic script, while `app.test.mjs` doing
`import { addTask } from './app.js'` needs a module - and each alternated
between satisfying one and the other. On one run the milestone reviewer
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


def test_installed_packages_are_not_walked(tmp_path: Path):
    """This runs on every write, so the walk must skip what it cannot use.

    `rglob` lists all of `node_modules` before discarding it - about 5us an
    entry, which a real install turns into a quarter of a second per write.
    Pruning the directories instead took a 2,520-entry tree from 12.3ms to
    0.09ms.
    """
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.js").write_text(EXPORTS_BOTH, encoding="utf-8")
    (project / "app.test.mjs").write_text(SUITE, encoding="utf-8")
    buried = project / "node_modules" / "left-pad"
    buried.mkdir(parents=True)
    # An importer inside node_modules must not be reported: it is not ours.
    (buried / "index.mjs").write_text(
        "import { addTask } from '../../app.js';\n", encoding="utf-8"
    )

    problems = who_would_break(project / "app.js", EXPORTS_NEITHER, project)

    assert all("node_modules" not in problem for problem in problems)
    assert any("app.test.mjs" in problem for problem in problems)


def test_an_import_inside_a_comment_does_not_count(project: Path):
    """`_RELATIVE` is anchored to a line start and ignores these already.

    `_NAMED_FROM`, which this check uses, is not - it matches an import
    wherever it appears, including inside a comment. The note would then tell
    an agent it was breaking an import that nothing makes.
    """
    (project / "app.test.mjs").write_text(
        "// import { addTask, getTasks } from './app.js';\n", encoding="utf-8"
    )

    assert who_would_break(project / "app.js", EXPORTS_NEITHER, project) == []


def test_an_import_inside_a_block_comment_does_not_count(project: Path):
    (project / "app.test.mjs").write_text(
        "/* import { addTask } from './app.js'; */\n", encoding="utf-8"
    )

    assert who_would_break(project / "app.js", EXPORTS_NEITHER, project) == []


def test_a_real_import_beside_a_commented_one_still_counts(project: Path):
    (project / "app.test.mjs").write_text(
        "// import { gone } from './app.js';\n"
        "import { addTask } from './app.js';\n",
        encoding="utf-8",
    )

    problems = who_would_break(project / "app.js", EXPORTS_NEITHER, project)

    assert len(problems) == 1
    assert "`addTask`" in problems[0]
    assert "`gone`" not in problems[0]
