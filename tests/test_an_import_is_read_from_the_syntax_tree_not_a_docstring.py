"""Undeclared packages are read from a Python file's syntax tree, and a local module is never one.

Measured on a Measure run: a docstring line "import of ``app.main`` which would
trigger..." raised a package called `of`, and the fast rewrite declared
`of==0.0.1` in the manifest.
"""
from __future__ import annotations

from app.analysis import dependency_drift


def test_prose_in_a_docstring_is_no_import_and_real_imports_are(tmp_path):
    project = tmp_path / "app"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "routes.py").write_text(
        '"""Routes.\n\n    import of ``pkg.main`` which would trigger re-execution of its\n    startup.\n"""\n'
        "import bcrypt\nfrom fastapi import APIRouter\nimport os, requests\nfrom . import models\n"
    )
    imported = dependency_drift._imports_in_source((project / "pkg" / "routes.py").read_text())
    assert "of" not in imported and {"bcrypt", "fastapi", "os", "requests"} <= set(imported)


def test_a_namespace_package_a_sibling_module_and_the_test_tree_are_local(tmp_path):
    project = tmp_path / "app"
    (project / "src" / "models").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "tests" / "conftest.py").write_text("x = 1\n")
    (project / "tests" / "helpers.py").write_text("y = 2\n")
    script = project / "tests" / "test_x.py"
    script.write_text("import conftest\nimport helpers\nfrom src import models\nimport models\nimport requests\n")
    local = lambda m: dependency_drift._a_local_module(project, script, m)
    assert local("conftest") and local("helpers") and local("src") and local("models") and not local("requests")


def test_a_project_module_imported_by_the_wrong_path_is_no_package_to_declare(tmp_path):
    """`from database import` in the tests, for `tasks_api/database.py`, was reported as an undeclared
    package `database`."""
    project = tmp_path / "tasks-api"
    (project / "tasks_api").mkdir(parents=True)
    (project / "tasks_api" / "database.py").write_text("def init_db():\n    pass\n")
    (project / "tests").mkdir()
    script = project / "tests" / "test_database.py"
    script.write_text("from database import init_db\nimport bcrypt\n")
    assert dependency_drift._a_local_module(project, script, "database")
    assert not dependency_drift._a_local_module(project, script, "bcrypt")
