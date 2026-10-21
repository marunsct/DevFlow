"""A rewriting fix never takes a file the project's ignore rules exclude - a test report, a build - as its target.

Measured live: two fixes in a row took `test-results/acceptance.xml`, named in
the failure text, as the file to rewrite, rewrote the runner's report, and left
both defects open.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.graph.rewritten_fixes import files_to_fix


def _project(root: Path) -> None:
    (root / "tasks-api" / "tasks_api").mkdir(parents=True)
    (root / "tasks-api" / "test-results").mkdir()
    (root / "tasks-api" / "tasks_api" / "app.py").write_text("app = None\n")
    (root / "tasks-api" / "test-results" / "acceptance.xml").write_text("<testsuites/>\n")
    (root / "tasks-api" / ".gitignore").write_text("test-results/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def test_the_report_is_left_and_the_source_is_taken(tmp_path: Path):
    _project(tmp_path)
    defect = SimpleNamespace(description="[AC-5] Mark one of your items done", affected_files=[])
    failure = ("AC-5 `test_ac5_mark_done`: see tasks-api/test-results/acceptance.xml\n"
               "tasks-api/tasks_api/app.py:12: AttributeError")

    chosen = files_to_fix(defect, failure, tmp_path, lambda relative: True)

    assert chosen == ["tasks-api/tasks_api/app.py"]


def test_without_a_repository_nothing_is_taken_for_ignored(tmp_path: Path):
    (tmp_path / "tasks-api" / "tasks_api").mkdir(parents=True)
    (tmp_path / "tasks-api" / "tasks_api" / "app.py").write_text("app = None\n")
    defect = SimpleNamespace(description="[AC-5] Mark done", affected_files=[])

    assert files_to_fix(defect, "tasks-api/tasks_api/app.py:3: Error", tmp_path, lambda r: True) == ["tasks-api/tasks_api/app.py"]
