"""A stage under the project memory reads no more of the project at its start than it needs to.

Under the memory a stage is given from the snapshot only the notice that the
project is empty. The snapshot was built in full all the same - every file of
the project read - and thrown away: on a large project, the whole of it read
at the start of every stage.
"""
from __future__ import annotations

from pathlib import Path

from app.agents import project_snapshot


def _project(tmp_path: Path, files: int) -> Path:
    (tmp_path / "shop").mkdir()
    (tmp_path / ".project-directory").write_text("shop\n")
    for n in range(files):
        (tmp_path / "shop" / f"m{n}.py").write_text(f"x = {n}\n")
    return tmp_path


def _reads(monkeypatch) -> list[Path]:
    read: list[Path] = []
    original = project_snapshot._readable

    def counting(path: Path):
        read.append(path)
        return original(path)

    monkeypatch.setattr(project_snapshot, "_readable", counting)
    return read


def test_under_the_memory_one_file_with_content_is_enough(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_MEMORY", raising=False)
    root = _project(tmp_path, 50)
    read = _reads(monkeypatch)

    assert project_snapshot.for_a_stage(root) == ""
    assert len(read) == 1


def test_an_empty_project_is_still_said_to_be_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_MEMORY", raising=False)
    root = _project(tmp_path, 0)
    (root / "shop" / "blank.py").write_text("\n")

    assert project_snapshot.for_a_stage(root).startswith("The project directory `shop/` has no files yet")


def test_without_the_memory_the_snapshot_is_built_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_MEMORY", "off")
    root = _project(tmp_path, 3)

    assert "--- shop/m0.py (1 lines) ---" in project_snapshot.for_a_stage(root)
