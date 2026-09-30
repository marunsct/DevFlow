"""A specialist may not write a file the plan gave to another work order.

On one run's first milestone the testing task wrote the backend task's
`app.js` before the backend task did, and the documentation task wrote the
testing task's unit test. Nothing here names a language or a framework.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    HARNESS_FILES,
    WORK_ORDER_FILES,
    RepositoryToolError,
    record_work_order_files,
    write_approved_artifact,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / ".project-directory").write_text("shop\n", encoding="utf-8")
    (tmp_path / "shop").mkdir()
    record_work_order_files(tmp_path, {
        "/shop/core.py": "specialist_backend_1",
        "tests/": "specialist_testing_2",
        "README.md": "specialist_documentation_3",
    })
    return tmp_path


def _as(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: stage)


def test_another_work_order_s_file_is_refused_with_its_owner(workspace: Path, monkeypatch) -> None:
    _as(monkeypatch, "specialist_testing_2")
    with pytest.raises(RepositoryToolError, match="the plan gave it to specialist_backend_1"):
        write_approved_artifact(workspace, "shop/core.py", "X = 1\n")
    assert not (workspace / "shop" / "core.py").exists()


def test_the_owner_writes_it_and_everything_else_stays_open(workspace: Path, monkeypatch) -> None:
    _as(monkeypatch, "specialist_backend_1")
    write_approved_artifact(workspace, "shop/core.py", "X = 1\n")
    write_approved_artifact(workspace, "shop/pyproject.toml", "[project]\n")
    assert (workspace / "shop" / "core.py").is_file()


def test_a_directory_and_a_bare_name_are_owned_too(workspace: Path, monkeypatch) -> None:
    _as(monkeypatch, "specialist_documentation_3")
    with pytest.raises(RepositoryToolError, match="specialist_testing_2"):
        write_approved_artifact(workspace, "shop/tests/test_core.py", "def test_x():\n    assert True\n")
    _as(monkeypatch, "specialist_backend_1")
    with pytest.raises(RepositoryToolError, match="specialist_documentation_3"):
        write_approved_artifact(workspace, "shop/README.md", "# Shop\n")


@pytest.mark.parametrize("stage", ["test_round_0", "defect_fix_1_0", ""])
def test_stages_outside_the_fan_out_are_not_held_to_it(workspace: Path, monkeypatch, stage: str) -> None:
    _as(monkeypatch, stage)
    write_approved_artifact(workspace, "shop/README.md", "# Shop\n")
    assert (workspace / "shop" / "README.md").is_file()


def test_the_record_is_harness_bookkeeping() -> None:
    assert WORK_ORDER_FILES in HARNESS_FILES
