"""The harness's inline scratch files are not scanned for packages no manifest declares.

Measured on two lessons proposed from the finding: the check reported `textkit` (the product's own package) and `glob`
as imports no manifest declares, from `tmp-inline-<hash>.py` and `.cjs` files a command's inline code was written to.
"""
from __future__ import annotations

from app.analysis import dependency_drift


def test_a_python_scratch_file_is_not_the_products_import(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "tmp-inline-95ae7701.py").write_text("import notadeclaredpackage\n")

    assert dependency_drift.undeclared(tmp_path) == []


def test_a_javascript_scratch_file_is_not_the_products_import(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^5"}}')
    (tmp_path / "tmp-inline-7b0f9185.cjs").write_text("const g = require('notdeclared');\n")

    assert dependency_drift.undeclared(tmp_path) == []


def test_a_real_undeclared_import_is_still_found(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "app.py").write_text("import notadeclaredpackage\n")

    assert [name for name, _, _ in dependency_drift.undeclared(tmp_path)] == ["notadeclaredpackage"]
