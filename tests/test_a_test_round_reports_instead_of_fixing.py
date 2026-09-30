"""A test round reports a product fault as a defect; it does not fix it.

On one run the test round's engineer edited the product's `app.js` to get a
failing unit test through. The fix was recorded nowhere: no defect, no owner,
no line in the Sprint Record. Nothing here names a language or a framework.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import RepositoryToolError, edit_approved_artifact, write_approved_artifact


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shop" / "tests").mkdir(parents=True)
    (tmp_path / "shop" / "cart.py").write_text("TOTAL = 0\n", encoding="utf-8")
    (tmp_path / "shop" / "tests" / "test_cart.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    return tmp_path


def _in_stage(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: name)


def test_a_test_round_may_not_change_product_code(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _in_stage(monkeypatch, "test_round_0")
    with pytest.raises(RepositoryToolError, match="this is a test round"):
        edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    with pytest.raises(RepositoryToolError, match="Report it in `defects`"):
        write_approved_artifact(project, "shop/cart.py", "TOTAL = 1\n")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 0\n"


@pytest.mark.parametrize("path", ["shop/tests/test_cart.py", "shop/pyproject.toml", "shop/NOTES.md"])
def test_its_tests_configuration_and_notes_are_its_own(project: Path, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    _in_stage(monkeypatch, "test_round_1")
    write_approved_artifact(project, path, "[x]\n" if path.endswith(".toml") else "def test_y():\n    assert True\n")
    assert (project / path).is_file()


@pytest.mark.parametrize("stage", ["defect_fix_1_0", "specialist_backend_1", ""])
def test_every_other_stage_changes_product_code_as_before(project: Path, monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    _in_stage(monkeypatch, stage)
    edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 1\n"


def test_a_test_round_may_not_delete_or_move_product_code(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused the write, a stage can take the file away instead - one run's
    specialist did exactly that with another task's module."""
    from app.tools.repository import delete_approved_artifact, move_approved_artifact

    _in_stage(monkeypatch, "test_round_0")
    with pytest.raises(RepositoryToolError, match="Nothing was deleted."):
        delete_approved_artifact(project, "shop/cart.py")
    with pytest.raises(RepositoryToolError, match="Nothing was moved."):
        move_approved_artifact(project, "shop/cart.py", "shop/cart_old.py")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 0\n"
