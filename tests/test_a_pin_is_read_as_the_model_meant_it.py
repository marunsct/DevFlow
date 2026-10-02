"""Two ways a correct line edit was refused for its pin, from one run's fix stage.

A pin - `expect_start` - is a line of the file sent inside a JSON string, and
is checked loosely on purpose: a strict comparison would put back the exact
transcription `replace_lines` exists to remove.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    replace_approved_lines,
    write_approved_artifact,
)

MANIFEST = (
    '{\n'
    '  "name": "app",\n'
    '  "version": "1.0.0",\n'
    '  "type": "module",\n'
    '  "scripts": {\n'
    '    "test": "node --test store.test.js"\n'
    '  }\n'
    '}\n'
)

SUITE = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert/strict';\n"
    "import { createTask } from './store.js';\n\n"
    "test('creates a task', () => {\n"
    "  const task = createTask('Buy milk');\n"
    "  assert.strictEqual(task.title, 'Buy milk');\n"
    "  assert.strictEqual(task.completed, false);\n"
    "});\n"
)


def _project(root: Path) -> None:
    write_approved_artifact(root, "app/package.json", MANIFEST)
    write_approved_artifact(root, "app/store.js", "export function createTask(t) { return { title: t, completed: false }; }\n")
    write_approved_artifact(root, "app/store.test.js", SUITE)


def test_a_pin_whose_quotes_were_escaped_twice_is_the_line_it_names(tmp_path: Path) -> None:
    """As the run sent it: the right line, the right replacement, and a pin
    carrying a backslash before every quote. It was told the line was "not in
    the file at all now"."""
    _project(tmp_path)

    replace_approved_lines(
        tmp_path, "app/package.json", 6, 6,
        '    "test": "node --test ./store.test.js"\n',
        expect_start='    "test\\": \\"node --test store.test.js\\"',
    )

    assert '"test": "node --test ./store.test.js"' in (tmp_path / "app" / "package.json").read_text(encoding="utf-8")


def test_a_backslash_the_file_really_holds_is_matched_as_sent(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "app/package.json", MANIFEST)
    write_approved_artifact(tmp_path, "app/a.js", 'const a = "say \\"hi\\"";\nconst b = 2;\n')

    replace_approved_lines(
        tmp_path, "app/a.js", 1, 1, 'const a = "hello";\n', expect_start='const a = "say \\"hi\\"";',
    )

    assert (tmp_path / "app" / "a.js").read_text(encoding="utf-8").startswith('const a = "hello";')


def test_a_pin_that_is_no_line_of_the_file_either_way_is_still_refused(tmp_path: Path) -> None:
    _project(tmp_path)

    with pytest.raises(RepositoryToolError):
        replace_approved_lines(
            tmp_path, "app/package.json", 6, 6, '    "test": "x"\n',
            expect_start='    "test\\": \\"mocha\\"',
        )


def test_a_pin_on_the_line_above_is_not_answered_by_moving_the_edit_there(tmp_path: Path) -> None:
    """Line 8 is the assertion the content comments out; the pin quotes line 7.
    The refusal used to say "send the same call with start_line=7", which would
    have replaced the wrong assertion."""
    _project(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(
            tmp_path, "app/store.test.js", 8, 8,
            "  // assert.strictEqual(task.completed, false);\n",
            expect_start="  assert.strictEqual(task.title, 'Buy milk');",
        )

    said = str(refused.value)
    assert "reads as line 8 rewritten" in said
    assert "Do not move `start_line`" in said
    assert "assert.strictEqual(task.completed, false);" in said
    assert "start_line=7" not in said
    assert (tmp_path / "app" / "store.test.js").read_text(encoding="utf-8") == SUITE


def test_a_line_that_really_moved_is_still_pointed_to(tmp_path: Path) -> None:
    _project(tmp_path)

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(
            tmp_path, "app/store.test.js", 8, 8,
            "  assert.strictEqual(task.title, 'Buy bread');\n",
            expect_start="  assert.strictEqual(task.title, 'Buy milk');",
        )

    assert "It is line 7 now" in str(refused.value)
