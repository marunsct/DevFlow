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


# --- taking the file away instead ---------------------------------------
#
# Measured on one run: the interface task, refused a write to the data task's
# `taskModel.js`, deleted it with `delete_artifact`, and wrote it again.


def test_another_work_order_s_file_cannot_be_deleted(workspace: Path, monkeypatch) -> None:
    from app.tools.repository import delete_approved_artifact

    (workspace / "shop" / "core.py").write_text("X = 1\n", encoding="utf-8")
    _as(monkeypatch, "specialist_ui_ux_0")

    with pytest.raises(RepositoryToolError, match="the plan gave it to specialist_backend_1") as refused:
        delete_approved_artifact(workspace, "shop/core.py")

    assert "Nothing was deleted." in str(refused.value)
    assert (workspace / "shop" / "core.py").read_text(encoding="utf-8") == "X = 1\n"


def test_another_work_order_s_file_cannot_be_moved_away(workspace: Path, monkeypatch) -> None:
    from app.tools.repository import move_approved_artifact

    (workspace / "shop" / "core.py").write_text("X = 1\n", encoding="utf-8")
    _as(monkeypatch, "specialist_ui_ux_0")

    with pytest.raises(RepositoryToolError, match="Nothing was moved."):
        move_approved_artifact(workspace, "shop/core.py", "shop/old_core.py")

    assert (workspace / "shop" / "core.py").is_file()
    assert not (workspace / "shop" / "old_core.py").exists()


def test_a_file_cannot_be_moved_onto_another_work_order_s_path(workspace: Path, monkeypatch) -> None:
    from app.tools.repository import move_approved_artifact

    (workspace / "shop" / "draft.py").write_text("X = 2\n", encoding="utf-8")
    _as(monkeypatch, "specialist_ui_ux_0")

    with pytest.raises(RepositoryToolError, match="specialist_backend_1"):
        move_approved_artifact(workspace, "shop/draft.py", "shop/core.py")

    assert not (workspace / "shop" / "core.py").exists()


def test_the_owner_still_deletes_and_moves_its_own_file(workspace: Path, monkeypatch) -> None:
    from app.tools.repository import delete_approved_artifact, move_approved_artifact

    (workspace / "shop" / "core.py").write_text("X = 1\n", encoding="utf-8")
    (workspace / "shop" / "scratch.py").write_text("print(1)\n", encoding="utf-8")
    _as(monkeypatch, "specialist_backend_1")

    move_approved_artifact(workspace, "shop/scratch.py", "shop/core_draft.py")
    delete_approved_artifact(workspace, "shop/core.py")

    assert not (workspace / "shop" / "core.py").exists()
    assert (workspace / "shop" / "core_draft.py").is_file()


def test_a_file_no_work_order_lists_is_still_anyone_s_to_delete(workspace: Path, monkeypatch) -> None:
    from app.tools.repository import delete_approved_artifact

    (workspace / "shop" / "probe.py").write_text("print(1)\n", encoding="utf-8")
    _as(monkeypatch, "specialist_ui_ux_0")

    delete_approved_artifact(workspace, "shop/probe.py")

    assert not (workspace / "shop" / "probe.py").exists()


def test_a_file_refused_again_and_again_says_how_many_times(workspace: Path, monkeypatch) -> None:
    """One run's backend specialist was refused the interface's `src/ui.js` six
    times, each a different change, so no repeat note ever fired."""
    from app.agents.stage_memory import forget_everything, remembering

    forget_everything()
    _as(monkeypatch, "specialist_testing_2")
    messages = []
    with remembering("thread-1:specialist_testing_2:abc"):
        for n in range(3):
            with pytest.raises(RepositoryToolError) as refused:
                write_approved_artifact(workspace, "shop/core.py", f"X = {n}\n")
            messages.append(str(refused.value))

    assert "times" not in messages[0] and "times" not in messages[1]
    assert messages[2].startswith("This stage has now been refused 'shop/core.py' 3 times")
    assert "the plan gave it to specialist_backend_1" in messages[2]
