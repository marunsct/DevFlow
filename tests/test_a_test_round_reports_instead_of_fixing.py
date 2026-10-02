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


# --- the testing work order is held to the same line ---------------------
#
# Measured over 25 runs: testing specialists wrote product code nine times - a
# page, an `app.js`, a server - and on one run wrote a stub `src/ui.js` that no
# work order listed, over the version another stage had just written.


def test_the_testing_work_order_may_not_change_product_code(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.tools.repository import delete_approved_artifact

    _in_stage(monkeypatch, "specialist_testing_3")
    with pytest.raises(RepositoryToolError, match="this is the testing work order") as refused:
        write_approved_artifact(project, "shop/cart.py", "TOTAL = 1\n")
    assert "`blockers`" in str(refused.value) and "Nothing was written." in str(refused.value)
    with pytest.raises(RepositoryToolError, match="testing work order"):
        edit_approved_artifact(project, "shop/cart.py", "TOTAL = 0", "TOTAL = 1")
    with pytest.raises(RepositoryToolError, match="Nothing was deleted."):
        delete_approved_artifact(project, "shop/cart.py")
    assert (project / "shop" / "cart.py").read_text(encoding="utf-8") == "TOTAL = 0\n"


@pytest.mark.parametrize("path", ["shop/tests/test_cart.py", "shop/pyproject.toml", "shop/NOTES.md"])
def test_the_testing_work_order_keeps_its_tests_and_configuration(
    project: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    _in_stage(monkeypatch, "specialist_testing_2")
    write_approved_artifact(project, path, "[x]\n" if path.endswith(".toml") else "def test_y():\n    assert True\n")
    assert (project / path).is_file()


def test_the_testing_work_order_is_told_before_it_tries() -> None:
    from app.agents.technical_lead import SpecialistTask
    from app.analysis.work_orders import contract_for_testing

    testing = SpecialistTask(specialist_role="testing", task_description="Write the tests.")
    code = SpecialistTask(specialist_role="backend", task_description="Write the code.")

    text = contract_for_testing(testing, [code, testing])

    assert "What is yours to change" in text and "`blockers`" in text
    assert contract_for_testing(code, [code, testing]) == ""


def test_a_moved_file_keeps_who_created_it(tmp_path: Path) -> None:
    from app.analysis import project_memory

    project_memory.record(tmp_path, "shop/debug.test.js", "specialist_testing_2")
    project_memory.record_move(tmp_path, "shop/debug.test.js", "shop/debug.js")

    assert project_memory.who_created(tmp_path, "shop/debug.js") == "specialist_testing_2"
    assert project_memory.who_created(tmp_path, "shop/debug.test.js") == ""


def test_the_testing_work_order_deletes_only_code_it_created(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Its own renamed probe goes; another stage's module stays."""
    from app.analysis import project_memory
    from app.tools.repository import delete_approved_artifact

    (project / "shop" / "probe.py").write_text("print(1)\n", encoding="utf-8")
    project_memory.record(project, "shop/probe.py", "specialist_testing_2")
    project_memory.record(project, "shop/cart.py", "specialist_backend_1")
    _in_stage(monkeypatch, "specialist_testing_2")

    delete_approved_artifact(project, "shop/probe.py")
    with pytest.raises(RepositoryToolError, match="testing work order"):
        delete_approved_artifact(project, "shop/cart.py")

    assert not (project / "shop" / "probe.py").exists()
    assert (project / "shop" / "cart.py").is_file()


DEFECT_REPORT = (
    "# Defect Report\n\n"
    "## 1. End-to-end tests fail\n"
    "- **Severity**: Critical\n"
    "- **Reproduction Steps**: run the suite\n"
    "- **Expected Behavior**: the server starts\n"
    "- **Actual Behavior**: it does not\n"
    "- **Affected Files**: shop/package.json\n"
    "- **Owner**: testing\n"
)


def test_a_test_round_does_not_write_its_findings_as_a_file(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One run's test round wrote `defects_report.md` into the project - the
    `defects` field, word for word - and it shipped with the product."""
    _in_stage(monkeypatch, "test_round_0")

    with pytest.raises(RepositoryToolError, match="returned in `defects`, not written to a file"):
        write_approved_artifact(project, "shop/defects_report.md", DEFECT_REPORT)

    assert not (project / "shop" / "defects_report.md").exists()


def test_another_stage_may_write_such_a_document(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _in_stage(monkeypatch, "specialist_documentation_1")

    write_approved_artifact(project, "shop/KNOWN_ISSUES.md", DEFECT_REPORT)

    assert (project / "shop" / "KNOWN_ISSUES.md").is_file()
