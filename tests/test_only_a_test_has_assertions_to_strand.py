"""The stranded-suite note belongs to test files and to nothing else.

`_the_test_command_will_not_run_this` fires on every write, and told the
application file, the stylesheet and the manifest that "this one's assertions
never execute" and to "Add it to the script".

Counted across the twelve stored transcripts plus one run: it fired 215
times on files that are not tests and 41 times on files that are. `app.js`
alone was told 83 times - and doing what it said would put the application
file into `node --test`. Four firings in five were false, in every run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import _the_test_command_will_not_run_this


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        '{"name":"p","scripts":{"test":"node --test app.test.mjs"}}', encoding="utf-8"
    )
    return tmp_path


def test_a_stranded_suite_is_still_told(project: Path) -> None:
    (project / "store.test.mjs").write_text("import {test} from 'node:test';", encoding="utf-8")

    note = _the_test_command_will_not_run_this(project / "store.test.mjs")

    assert "will not reach 'store.test.mjs'" in note


def test_the_application_file_is_not(project: Path) -> None:
    """83 of the false firings were this file."""
    (project / "app.js").write_text("export function addTask() {}", encoding="utf-8")

    assert _the_test_command_will_not_run_this(project / "app.js") == ""


def test_the_manifest_is_not(project: Path) -> None:
    assert _the_test_command_will_not_run_this(project / "package.json") == ""


def test_the_stylesheet_is_not(project: Path) -> None:
    (project / "styles.css").write_text(":root { --bg: #fff; }", encoding="utf-8")

    assert _the_test_command_will_not_run_this(project / "styles.css") == ""


def test_the_page_is_not(project: Path) -> None:
    (project / "index.html").write_text("<!doctype html>", encoding="utf-8")

    assert _the_test_command_will_not_run_this(project / "index.html") == ""


def test_the_named_suite_itself_is_still_silent(project: Path) -> None:
    """It is in the command, so nothing is stranded."""
    (project / "app.test.mjs").write_text("import {test} from 'node:test';", encoding="utf-8")

    assert _the_test_command_will_not_run_this(project / "app.test.mjs") == ""
