"""A test file the runner will never collect.

run-d3965815's security specialist wrote `todo-app/app.test_xss.mjs`: real
assertions, for a real XSS concern. `node --test todo-app/` collected
`app.test.mjs` and reported "# tests 1" while two test files sat in the
directory. Nothing failed, because an uncollected test does not error - it is
simply absent, and the testing round, the milestone review and the defect loop
all read a green result that never included it.
"""

from __future__ import annotations

import pytest

from app.analysis.test_discovery import undiscoverable_test

NODE_TEST = (
    "import test from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "test('escapes markup', () => assert.ok(true));\n"
)


def test_the_file_from_run_d3965815_is_caught() -> None:
    note = undiscoverable_test("todo-app/app.test_xss.mjs", NODE_TEST)

    assert note is not None
    assert "will not collect it" in note
    assert "app-xss.test.mjs" in note, "a name that works must be offered"


@pytest.mark.parametrize(
    "path",
    [
        "todo-app/app.test.mjs",
        "todo-app/app.test.js",
        "todo-app/app.test.cjs",
        "todo-app/app-test.mjs",
        "todo-app/app_test.mjs",
        "todo-app/test-xss.mjs",
        "todo-app/test.mjs",
        "todo-app/test/anything.mjs",
        "todo-app/tests/anything.mjs",
        "todo-app/__tests__/anything.mjs",
    ],
)
def test_a_name_node_collects_is_left_alone(path: str) -> None:
    """Node's documented default patterns, each one."""
    assert undiscoverable_test(path, NODE_TEST) is None


@pytest.mark.parametrize(
    ("path", "content"),
    [
        # Another runner, with its own patterns and its own config file.
        ("src/Widget.spec.ts", "import { describe, it } from 'vitest';\n"),
        ("src/Widget.spec.mjs", "import { describe } from 'vitest';\n"),
        # An application module that happens to export something called `test`.
        ("todo-app/app.mjs", "export function test(a) { return a; }\ntest(1);\n"),
        # Not JavaScript at all.
        ("todo-app/style.css", ".a { color: red }"),
        ("scripts/check.py", "import pytest\n"),
        # Empty.
        ("todo-app/thing.mjs", ""),
    ],
)
def test_what_this_must_not_warn_about(path: str, content: str) -> None:
    """A wrong warning about a file that runs fine is worse than no warning."""
    assert undiscoverable_test(path, content) is None


def test_a_plausible_name_that_still_does_not_match() -> None:
    """`security.mjs` is a perfectly reasonable name and is never collected."""
    note = undiscoverable_test("todo-app/security.mjs", NODE_TEST)

    assert note is not None
    assert "security.test.mjs" in note


def test_the_note_reaches_the_write(tmp_path) -> None:
    from app.tools.repository import write_approved_artifact

    write_approved_artifact(tmp_path, "todo-app/package.json", '{"name": "todo-app"}')

    result = write_approved_artifact(tmp_path, "todo-app/app.test_xss.mjs", NODE_TEST)

    assert "will not collect it" in (result.get("note") or "")
