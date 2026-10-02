"""The debugging scripts finished stages leave behind are removed by the harness.

Measured over one day: every run that reached a second fix stage carried
throwaway scripts into its test rounds - `tmp_test.js`, `tmp_simulate.js`,
`debug_run.js`, twenty in one project. The stages are told to delete them and
often do not, and a finding that asks for it costs a stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import project_memory
from app.tools.repository import PROJECT_MARKER, clear_the_throwaways_left_behind


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    project = tmp_path / "the-app"
    (project / "tests").mkdir(parents=True)
    (tmp_path / PROJECT_MARKER).write_text("the-app\n", encoding="utf-8")
    (project / "app.js").write_text("export const add = (a, b) => a + b;\n", encoding="utf-8")
    (project / "package.json").write_text('{"scripts": {"test": "node --test"}}\n', encoding="utf-8")
    return tmp_path


def _wrote(root: Path, relative: str, content: str = "console.log(1);\n", stage: str = "defect_fix_1_0") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if stage:
        project_memory.record(root, relative, stage)
    return path


def test_a_stage_s_throwaways_are_removed(workspace) -> None:
    probes = [_wrote(workspace, f"the-app/{name}") for name in ("tmp_test.js", "debug_run.js", "tests/tmp_check.js")]

    removed = clear_the_throwaways_left_behind(workspace)

    assert sorted(removed) == ["the-app/debug_run.js", "the-app/tests/tmp_check.js", "the-app/tmp_test.js"]
    assert not any(path.exists() for path in probes)
    assert (workspace / "the-app" / "app.js").exists()


def test_one_something_still_refers_to_is_kept(workspace) -> None:
    kept = _wrote(workspace, "the-app/tmp_server.js")
    (workspace / "the-app" / "package.json").write_text(
        '{"scripts": {"serve": "node tmp_server.js"}}\n', encoding="utf-8"
    )

    assert clear_the_throwaways_left_behind(workspace) == []
    assert kept.exists()


def test_a_file_no_stage_of_this_run_created_is_kept(workspace) -> None:
    """A seeded codebase's own files are not this run's to delete."""
    kept = _wrote(workspace, "the-app/tmp_fixture.js", stage="")

    assert clear_the_throwaways_left_behind(workspace) == []
    assert kept.exists()


def test_ordinary_files_and_deliberate_script_directories_are_kept(workspace) -> None:
    ordinary = _wrote(workspace, "the-app/storage.js")
    tool = _wrote(workspace, "the-app/tools/debug-linecount.mjs")
    installed = _wrote(workspace, "the-app/node_modules/pkg/tmp_build.js")

    assert clear_the_throwaways_left_behind(workspace) == []
    assert ordinary.exists() and tool.exists() and installed.exists()


def test_nothing_is_touched_outside_the_pinned_project(workspace) -> None:
    outside = _wrote(workspace, "tmp_notes.js")

    assert clear_the_throwaways_left_behind(workspace) == []
    assert outside.exists()
