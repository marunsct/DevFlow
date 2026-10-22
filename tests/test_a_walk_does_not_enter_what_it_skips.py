"""A workspace walk prunes the directories it ignores instead of filtering later.

See `app.analysis.walk`. The checks filtered `node_modules`, `.venv` and the
rest out of `rglob`'s results, so the walk itself still entered every one of
them - and a test that passed `/` as the repository root walked the whole
machine until the process died.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.analysis import walk
from app.analysis.walk import directories_under, files_under


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.html").write_text("<p>", encoding="utf-8")
    (tmp_path / "app" / "app.js").write_text("x", encoding="utf-8")
    (tmp_path / "app" / "tests").mkdir()
    (tmp_path / "app" / "tests" / "app.test.js").write_text("x", encoding="utf-8")
    deps = tmp_path / "app" / "node_modules" / "left-pad"
    deps.mkdir(parents=True)
    (deps / "index.js").write_text("x", encoding="utf-8")
    (deps / "package.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _relative(paths, root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in paths)


class TestWhatIsFound:
    def test_every_file_outside_the_skipped_directories(self, workspace: Path) -> None:
        assert _relative(files_under(workspace, {"node_modules"}), workspace) == [
            "app/app.js",
            "app/index.html",
            "app/tests/app.test.js",
        ]

    def test_a_name_pattern_matches_the_basename(self, workspace: Path) -> None:
        assert _relative(files_under(workspace, {"node_modules"}, "*.js"), workspace) == [
            "app/app.js",
            "app/tests/app.test.js",
        ]

    def test_an_exact_name(self, workspace: Path) -> None:
        found = _relative(files_under(workspace, {"node_modules"}, "package.json"), workspace)

        assert found == []

    def test_directories_too(self, workspace: Path) -> None:
        assert _relative(directories_under(workspace, {"node_modules"}, "tests"), workspace) == [
            "app/tests"
        ]

    def test_nothing_skipped_finds_everything(self, workspace: Path) -> None:
        assert "app/node_modules/left-pad/index.js" in _relative(files_under(workspace), workspace)


class TestWhatIsNeverEntered:
    def test_a_skipped_directory_is_not_listed_at_all(self, workspace: Path, monkeypatch) -> None:
        """The point of the module: pruned before entry, not filtered after."""
        listed: list[str] = []
        real = os.scandir

        def recording(path=".", *args, **kwargs):
            listed.append(os.fspath(path))
            return real(path, *args, **kwargs)

        monkeypatch.setattr(os, "scandir", recording)

        list(files_under(workspace, {"node_modules"}))

        assert not any("node_modules" in p for p in listed)

    def test_a_link_back_to_an_ancestor_is_not_followed(self, workspace: Path) -> None:
        (workspace / "app" / "loop").symlink_to(workspace, target_is_directory=True)

        found = _relative(files_under(workspace, {"node_modules"}), workspace)

        assert found == ["app/app.js", "app/index.html", "app/tests/app.test.js"]

    def test_an_unreadable_directory_is_passed_over(self, workspace: Path) -> None:
        locked = workspace / "locked"
        locked.mkdir()
        (locked / "secret.js").write_text("x", encoding="utf-8")
        locked.chmod(0)
        try:
            found = _relative(files_under(workspace, {"node_modules"}), workspace)
        finally:
            locked.chmod(0o755)

        assert "app/app.js" in found


def test_the_product_checks_use_it() -> None:
    """The walk every test round runs, over every file of the product."""
    import inspect

    from app.analysis import integration_checks

    assert "files_under(root, _SKIP)" in inspect.getsource(integration_checks._source_files)
    assert "rglob" not in inspect.getsource(integration_checks._source_files)
    assert walk.__doc__
