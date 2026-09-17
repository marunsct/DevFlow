"""A manifest script whose paths are relative to the wrong directory.

npm runs a script from the directory holding the `package.json`, so a path in
it is already relative to that directory. Writing the directory's own name
into the path doubles it, and the file is never found. The error says so
outright:

    Cannot find module '.../simple-to-do-list-app/simple-to-do-list-app/app.test.mjs'

Five of the fifty-six stored manifests do this and not one of their suites
reports anything at all - the stage reads `Could not find` as the product
being broken rather than the command being wrong.

`_manifest_scripts_that_cannot_resolve` reports it at a milestone review.
This refuses it at the write, where the fix is deleting one path segment.
"""

from __future__ import annotations

import json

import pytest

from app.tools.repository import RepositoryToolError, write_approved_artifact


def _write(tmp_path, directory: str, scripts: dict):
    project = tmp_path / directory
    project.mkdir(exist_ok=True)
    (project / "app.test.mjs").write_text("import { test } from 'node:test';\n")
    return write_approved_artifact(
        tmp_path, f"{directory}/package.json", json.dumps({"name": "x", "scripts": scripts})
    )


@pytest.mark.parametrize(
    "directory,command",
    [
        ("todo-app", "node --test todo-app/app.test.mjs"),
        ("simple-to-do-list-app", "node --test simple-to-do-list-app/app.test.mjs"),
        ("simple-to-do-list-app", "node --test simple-to-do-list-app/*.test.mjs"),
        ("simple-to-do-list-app", "node simple-to-do-list-app/app.test.js"),
    ],
)
def test_the_stored_forms_are_all_refused(tmp_path, directory, command):
    with pytest.raises(RepositoryToolError) as refusal:
        _write(tmp_path, directory, {"test": command})
    assert f"'{directory}/{directory}/" in str(refusal.value)
    assert f"Drop the leading '{directory}/'" in str(refusal.value)


@pytest.mark.parametrize(
    "command",
    [
        "node --test app.test.mjs",
        "node --test",
        "node --test tests/app.test.mjs",
        "node --test ./app.test.mjs",
    ],
)
def test_a_path_relative_to_the_right_place_is_written(tmp_path, command):
    _write(tmp_path, "todo-app", {"test": command})


def test_a_filename_that_merely_starts_with_the_directory_name(tmp_path):
    """A project called `app` must not collide with `app.test.mjs`; the name
    is matched as a whole path segment, so only `app/` counts."""
    _write(tmp_path, "app", {"test": "node --test app.test.mjs"})


def test_any_script_is_checked_not_only_test(tmp_path):
    with pytest.raises(RepositoryToolError) as refusal:
        _write(
            tmp_path,
            "todo-app",
            {"test": "node --test", "build": "cp todo-app/app.js dist/"},
        )
    assert "`build` script" in str(refusal.value)


def test_a_manifest_with_no_scripts_is_written(tmp_path):
    _write(tmp_path, "todo-app", {})


def test_a_non_string_script_does_not_break_the_check(tmp_path):
    project = tmp_path / "todo-app"
    project.mkdir()
    write_approved_artifact(
        tmp_path,
        "todo-app/package.json",
        json.dumps({"name": "x", "scripts": {"test": ["node", "--test"]}}),
    )
