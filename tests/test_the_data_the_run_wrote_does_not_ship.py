"""The data the run's own tests wrote does not ship with the product (harness review HR2.PR.11).

20 products carried `data/` (7 with a database), one with twelve notes its suite wrote, because `DATA_DIR` defaults
to a folder the run's own tests filled.
"""
from __future__ import annotations

import inspect
import os
import time

from app.graph import delivery
from app.stacks import release_audits


def _project(tmp_path, ignored=True):
    (tmp_path / "notes" / "data").mkdir(parents=True)
    if ignored:
        (tmp_path / "notes" / ".gitignore").write_text("node_modules/\ndata/\n")
    (tmp_path / "notes" / "data" / "notes.json").write_text('[{"title": "written by a test"}]')
    return tmp_path


def test_a_data_file_written_by_a_stage_ships_without_it(tmp_path) -> None:
    root = _project(tmp_path)
    started = time.time() - 60

    assert release_audits.remove_the_run_s_own_data(root, "notes", started) == ["notes/data"]
    assert (root / "notes" / "data").is_dir() and not any((root / "notes" / "data").iterdir())


def test_seed_data_older_than_the_run_is_kept_whole(tmp_path) -> None:
    root = _project(tmp_path)
    seed = root / "notes" / "data" / "seed.json"
    seed.write_text("[]")
    old = time.time() - 3600
    os.utime(seed, (old, old))

    assert release_audits.remove_the_run_s_own_data(root, "notes", time.time() - 60) == []
    assert (root / "notes" / "data" / "notes.json").exists() and seed.exists()


def test_a_folder_git_does_not_ignore_is_the_product_s_and_kept(tmp_path) -> None:
    root = _project(tmp_path, ignored=False)
    assert release_audits.remove_the_run_s_own_data(root, "notes", time.time() - 60) == []
    assert (root / "notes" / "data" / "notes.json").exists()


def test_the_declared_data_folder_is_read_from_the_specification(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Configuration\n- variable: STORE_DIR; type: Environment Variable; default: store/; description: x\n")
    assert release_audits.data_folders(tmp_path, "notes") == ["store", "data"]


def test_the_release_does_it_on_the_way_out() -> None:
    source = inspect.getsource(delivery.release)
    assert source.index("remove_the_run_s_own_data") < source.index("deferred = suite.deferred(root)")


def test_a_database_the_run_wrote_beside_the_code_does_not_ship(tmp_path) -> None:
    """Measured (hidden 10/10): the product wrote `tasks.db` beside its code, not under its data folder, and it shipped."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text("## File Plan\n- api/app/main.py: the service\n")
    (tmp_path / "api" / "app").mkdir(parents=True)
    (tmp_path / "api" / "app" / "main.py").write_text("x = 1\n")
    (tmp_path / "api" / "tasks.db").write_text("")
    assert release_audits.remove_the_run_s_own_data(tmp_path, "api", time.time() - 60) == ["api/tasks.db"]
    assert (tmp_path / "api" / "app" / "main.py").exists()


def test_a_database_the_file_plan_lists_stays(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text("## File Plan\n- api/seed.db: the records it ships with\n")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "seed.db").write_text("")
    assert release_audits.remove_the_run_s_own_data(tmp_path, "api", time.time() - 60) == []


def test_the_release_clears_the_data_again_after_measuring_again() -> None:
    source = inspect.getsource(delivery.release)
    measured = source.index("_measured_again_if_it_changed(root)")
    assert source.index("remove_the_run_s_own_data", measured) > measured
