"""An edit whose replacement contains its own `find` is not applied twice.

One run's `defect_fix_1_1` sent `find: "let tasks = [];"` with
`replace: "export let tasks = [];"` at 16:40, and again at 16:45. The second
send still matched - inside the replacement - and would have written
`export export let tasks = [];`. Node's parse check refused it; a file with no
such check would have been changed twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import edit_approved_artifact


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    return tmp_path


def _write(root: Path, name: str, text: str) -> Path:
    path = root / "app" / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_second_send_is_already_applied(project):
    path = _write(project, "store.js", "let tasks = [];\nexport function f() {}\n")
    edit_approved_artifact(project, "app/store.js", "let tasks = [];", "export let tasks = [];")

    result = edit_approved_artifact(project, "app/store.js", "let tasks = [];", "export let tasks = [];")

    assert result["status"] == "already_applied"
    assert path.read_text(encoding="utf-8").count("export let tasks") == 1
    assert "export export" not in path.read_text(encoding="utf-8")


def test_a_file_without_a_parse_check_is_not_changed_twice(project):
    """The case the parse check could not have saved."""
    path = _write(project, "styles.css", ".btn { color: red; }\n")
    edit_approved_artifact(project, "app/styles.css", "color: red;", "color: red; font-weight: bold;")

    result = edit_approved_artifact(
        project, "app/styles.css", "color: red;", "color: red; font-weight: bold;"
    )

    assert result["status"] == "already_applied"
    assert path.read_text(encoding="utf-8") == ".btn { color: red; font-weight: bold; }\n"


def test_find_at_the_end_of_the_replacement(project):
    path = _write(project, "notes.md", "# Title\nbody\n")
    edit_approved_artifact(project, "app/notes.md", "body\n", "intro\nbody\n")

    result = edit_approved_artifact(project, "app/notes.md", "body\n", "intro\nbody\n")

    assert result["status"] == "already_applied"
    assert path.read_text(encoding="utf-8") == "# Title\nintro\nbody\n"


def test_a_match_outside_the_replacement_is_still_edited(project):
    """Made in one place, not yet in the other: not applied."""
    from app.tools.repository import _where_the_replacement_already_wraps_every_match as wraps

    original = "export let a = 1;\nlet a = 1;\n"

    assert wraps(original, "let a = 1;", "export let a = 1;") == 0


def test_the_first_send_is_applied(project):
    path = _write(project, "store.js", "let tasks = [];\n")

    result = edit_approved_artifact(project, "app/store.js", "let tasks = [];", "export let tasks = [];")

    assert result["status"] == "edited"
    assert path.read_text(encoding="utf-8") == "export let tasks = [];\n"
