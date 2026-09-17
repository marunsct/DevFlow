"""A correctly-named test file the project's own command will not reach.

`undiscoverable_test` asks whether Node's patterns would collect the file.
This asks the other question, which a correctly-named file still fails:
whether the command the project actually runs reaches it.

A `test` script that names its files is the majority here - 17 of the 32
manifests across the stored workspaces - and every one excludes whatever is
written next. Twelve of fifty-five workspaces carry test files `npm test`
never runs, their assertions never executed while every gate reads a pass.

Run 1ae7671d is what that costs: its script ran three named files while the
project held six, `npm test` passed on the subset, the real failures survived
every green run, and the sprint exhausted all three remediation attempts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import write_approved_artifact

SUITE = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "import { addTask } from './app.js';\n"
    "test('adds', () => { assert.strictEqual(addTask('x', []).length, 1); });\n"
)


@pytest.fixture
def project(tmp_path: Path):
    def build(command: str) -> Path:
        (tmp_path / "todo").mkdir(exist_ok=True)
        write_approved_artifact(
            tmp_path, "todo/package.json", '{"name":"t","scripts":{"test":"%s"}}' % command
        )
        write_approved_artifact(
            tmp_path, "todo/app.js", "export function addTask(t, l) { return [...l, t]; }\n"
        )
        write_approved_artifact(tmp_path, "todo/app.test.mjs", SUITE)
        return tmp_path

    return build


def test_a_new_file_the_named_command_excludes_is_reported(project):
    root = project("node --test app.test.mjs")

    note = write_approved_artifact(root, "todo/app.filter.test.mjs", SUITE).get("note", "")

    assert "will not reach 'app.filter.test.mjs'" in note


def test_it_says_the_suite_will_pass_regardless(project):
    """That is the whole danger: nothing reports an uncollected test."""
    root = project("node --test app.test.mjs")

    note = write_approved_artifact(root, "todo/app.filter.test.mjs", SUITE).get("note", "")

    assert "assertions never execute" in note
    assert "node --test" in note


def test_rewriting_a_file_the_command_names_is_silent(project):
    root = project("node --test app.test.mjs")

    note = write_approved_artifact(root, "todo/app.test.mjs", SUITE).get("note", "")

    assert "will not reach" not in note


def test_a_discovery_command_is_silent(project):
    """`node --test` with no arguments searches the project; nothing is excluded."""
    root = project("node --test")

    note = write_approved_artifact(root, "todo/app.filter.test.mjs", SUITE).get("note", "")

    assert "will not reach" not in note


def test_a_file_the_command_already_lists_is_silent(project):
    root = project("node --test app.test.mjs app.filter.test.mjs")

    note = write_approved_artifact(root, "todo/app.filter.test.mjs", SUITE).get("note", "")

    assert "will not reach" not in note


def test_a_project_with_no_test_script_is_silent(tmp_path: Path):
    (tmp_path / "todo").mkdir()
    write_approved_artifact(tmp_path, "todo/package.json", '{"name":"t"}')
    write_approved_artifact(
        tmp_path, "todo/app.js", "export function addTask(t, l) { return [...l, t]; }\n"
    )

    note = write_approved_artifact(tmp_path, "todo/app.test.mjs", SUITE).get("note", "")

    assert "will not reach" not in note
