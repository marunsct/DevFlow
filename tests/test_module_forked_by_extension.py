"""The same module written twice, under two extensions.

`_supersedes_existing` catches `spec_v2.md` beside `spec.md`. This is the other
spelling of the same mistake, and the extension hides it.

One run ended a milestone with `simple-to-do-list-app/app.js` (4,887
bytes) and `simple-to-do-list-app/app.mjs` (4,853 bytes) - near-identical
copies of one application. From there every fix lands in one of them, the test
file imports whichever it imports, and half the remediation does nothing. That
run's two test rounds and its 57-call defect fix were spent on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import RepositoryToolError, write_approved_artifact

MODULE = (
    "export function loadTasks() {\n"
    "  return JSON.parse(localStorage.getItem('tasks') || '[]');\n"
    "}\n"
    "export function addTask(task) {\n"
    "  const all = loadTasks();\n"
    "  all.push(task);\n"
    "  localStorage.setItem('tasks', JSON.stringify(all));\n"
    "}\n"
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')
    return tmp_path


def test_a_copy_under_another_extension_is_refused(project: Path) -> None:
    write_approved_artifact(project, "proj/app.js", MODULE)

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(project, "proj/app.mjs", MODULE)

    message = str(caught.value)
    assert "'app.js' already holds this module" in message
    assert "move_artifact" in message, "the message must name the way to do it properly"
    assert not (project / "proj" / "app.mjs").exists()


def test_a_copy_that_has_since_been_edited_is_still_a_copy(project: Path) -> None:
    """A fork is edited after it is made; that is what makes it a fork."""
    write_approved_artifact(project, "proj/app.js", MODULE)

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(
            project, "proj/app.mjs", MODULE.replace("addTask", "addItem")
        )


def test_a_genuinely_different_module_is_written(project: Path) -> None:
    write_approved_artifact(project, "proj/app.js", MODULE)

    assert write_approved_artifact(
        project, "proj/util.mjs", "export const clamp = (n) => Math.max(0, n);\n"
    )["status"]


def test_a_different_module_that_shares_a_stem_is_written(project: Path) -> None:
    """Two files can share a stem across extensions and be different modules.
    Refusing one of those would be worse than allowing a fork."""
    write_approved_artifact(project, "proj/app.js", MODULE)

    assert write_approved_artifact(
        project,
        "proj/app.cjs",
        "// A CommonJS shim that re-exports nothing in common with the module.\n"
        "const os = require('os');\nmodule.exports = { platform: os.platform() };\n",
    )["status"]


def test_the_first_file_is_unaffected(project: Path) -> None:
    assert write_approved_artifact(project, "proj/app.mjs", MODULE)["status"]
    assert (project / "proj" / "app.mjs").read_text() == MODULE


@pytest.mark.parametrize("name", ["notes.md", "style.css", "data.json"])
def test_other_kinds_of_file_are_not_judged_this_way(project: Path, name: str) -> None:
    # Each a valid file of its kind: a stylesheet is read by its grammar now,
    # and "content" alone is not CSS.
    body = {"data.json": '{"a": 1}', "style.css": "body { margin: 0; }\n"}.get(name, "content\n")
    assert write_approved_artifact(project, f"proj/{name}", body)["status"]
