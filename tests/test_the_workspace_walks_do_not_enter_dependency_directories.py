"""The checks that look for the product's files do not walk into its dependencies.

Each did `rglob` over the project and threw away what was under
`node_modules`, `.venv` and the rest afterwards. The filter was right and the
walk was not: it still opened every directory in them, on every check, on every
round - tens of thousands of directories in a large codebase's dependencies,
for files none of these checks wanted. What each finds is unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import mutation, suite
from app.analysis import interface_checks, work_orders
from app.graph import delivery
from app.sprint import handover
from app.tools import repository


def _workspace(root: Path) -> Path:
    project = root / "shop"
    for folder in ("src", "acceptance", "docs"):
        (project / folder).mkdir(parents=True)
    (project / "src" / "app.js").write_text("export const go = () => 1\n")
    (project / "src" / "site.css").write_text("body {}\n")
    (project / "src" / "store_test.go").write_text("package src\n")
    (project / "acceptance" / "shop.spec.js").write_text("test('x', () => {})\n")
    (root / "docs").mkdir()
    (root / "docs" / "plan.md").write_text("# Plan\n")
    (root / ".project-directory").write_text("shop")
    for where in (project, project / "acceptance", root / "docs"):
        deep = where / "node_modules" / "left-pad" / "lib"
        deep.mkdir(parents=True)
        (deep / "index.js").write_text("module.exports = 1\n")
        (deep / "pad.spec.js").write_text("test('y', () => {})\n")
        (deep / "pad.css").write_text("a {}\n")
        (deep / "pad_test.go").write_text("package lib\n")
    (project / ".venv" / "lib").mkdir(parents=True)
    (project / ".venv" / "lib" / "site.js").write_text("x\n")
    return project


@pytest.fixture
def opened(monkeypatch):
    seen: list[str] = []
    real = os.scandir

    def recording(path="."):
        seen.append(os.fspath(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", recording)
    return seen


def _entered_dependencies(seen: list[str]) -> list[str]:
    return [p for p in seen if "node_modules" in Path(p).parts]


def test_the_suite_s_files(tmp_path, monkeypatch, opened):
    project = _workspace(tmp_path)
    monkeypatch.setattr(suite, "location", lambda root: ("shop", "acceptance"))
    monkeypatch.setattr(suite, "_the_report", lambda root: None)

    assert suite.suite_files(tmp_path) == [project / "acceptance" / "shop.spec.js"]
    assert _entered_dependencies(opened) == []


def test_the_source_mutation_testing_changes(tmp_path, opened):
    project = _workspace(tmp_path)

    found = mutation.source_files(project)

    assert project / "src" / "app.js" in found and not any("node_modules" in p.parts for p in found)
    assert _entered_dependencies(opened) == [] and not [p for p in opened if ".venv" in p]


def test_the_product_s_stylesheets(tmp_path, opened):
    project = _workspace(tmp_path)

    assert interface_checks._the_product_s(project, "*.css") == [project / "src" / "site.css"]
    assert _entered_dependencies(opened) == []


def test_whether_a_unit_test_exists_beside_the_code(tmp_path, opened):
    project = _workspace(tmp_path)
    pack = SimpleNamespace(unit_dir=".", unit_pattern="*_test.go")
    assert delivery._a_unit_test_file_exists(project, pack)
    (project / "src" / "store_test.go").unlink()
    opened.clear()

    # Only a dependency's own test is left: none of the product's.
    assert not delivery._a_unit_test_file_exists(project, pack)
    assert _entered_dependencies(opened) == []


def test_the_handover_pack_s_files(tmp_path, opened):
    _workspace(tmp_path)

    assert "docs/plan.md" in handover.files_of(tmp_path)
    assert _entered_dependencies(opened) == []


def test_the_files_a_sprint_names(tmp_path, opened):
    _workspace(tmp_path)

    work_orders._files_the_sprint_names_and_nobody_is_given("Change `app.js`.", [], tmp_path, "shop")

    assert _entered_dependencies(opened) == []


def test_the_throwaways_swept_after_a_stage(tmp_path, opened):
    _workspace(tmp_path)

    repository.clear_the_throwaways_left_behind(tmp_path)

    assert _entered_dependencies(opened) == []
