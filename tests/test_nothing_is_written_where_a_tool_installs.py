"""Nothing is written by hand into a directory a tool fills.

Measured on one run: `npm install jsdom` was refused, and the backend specialist
wrote `node_modules/jsdom/package.json` and `node_modules/jsdom/index.js` itself,
both accepted - so the tests would have run against a counterfeit library that
the next real install overwrites. Nothing here names a language or a framework.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    delete_approved_artifact,
    edit_approved_artifact,
    move_approved_artifact,
    replace_approved_lines,
    write_approved_artifact,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shop" / "node_modules" / "lib").mkdir(parents=True)
    (tmp_path / "shop" / "node_modules" / "lib" / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (tmp_path / "shop" / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("path", [
    "shop/node_modules/jsdom/index.js",
    "shop/.venv/lib/site.py",
    "shop/.git/config",
    "shop/__pycache__/x.py",
])
def test_a_write_there_is_refused(project: Path, path: str) -> None:
    with pytest.raises(RepositoryToolError, match="which a tool fills"):
        write_approved_artifact(project, path, "export class JSDOM {}\n")
    assert not (project / path).exists()


def test_an_edit_a_line_change_a_delete_and_a_move_are_refused_too(project: Path) -> None:
    installed = "shop/node_modules/lib/index.js"
    with pytest.raises(RepositoryToolError, match="which a tool fills"):
        edit_approved_artifact(project, installed, "1", "2")
    with pytest.raises(RepositoryToolError, match="which a tool fills"):
        replace_approved_lines(project, installed, 1, 1, "module.exports = 2;")
    with pytest.raises(RepositoryToolError, match="Nothing was deleted."):
        delete_approved_artifact(project, installed)
    with pytest.raises(RepositoryToolError, match="Nothing was moved."):
        move_approved_artifact(project, "shop/app.js", "shop/node_modules/app.js")
    assert (project / installed).read_text(encoding="utf-8") == "module.exports = 1;\n"
    assert (project / "shop" / "app.js").is_file()


@pytest.mark.parametrize("path", ["shop/build/make.py", "shop/env/settings.py", "shop/src/node_modules_notes.md"])
def test_a_project_s_own_folder_of_a_similar_name_is_still_writable(project: Path, path: str) -> None:
    write_approved_artifact(project, path, "x = 1\n")
    assert (project / path).is_file()
