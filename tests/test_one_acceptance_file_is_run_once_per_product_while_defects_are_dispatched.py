"""An acceptance file run for one defect is not run again for the next while the product is unchanged.

Measured on one web run: sixteen open defects were each re-measured at dispatch, one browser file at a time, and the
eight files they shared ran 53 times in 20 minutes on a product nothing had changed - before any fixer was sent. Each
file's run and the report it left are kept by the product's fingerprint; a defect asking for the same file of the same
product is judged from them, by its own criteria.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.acceptance import per_file, unstable

REPORT = """<?xml version="1.0"?><testsuites><testsuite name="pytest">
<testcase classname="acceptance.test_ac1_ac9" name="test_ac9_duplicate_username_returns_409"/>
<testcase classname="acceptance.test_ac1_ac9" name="test_ac8_item_shape"><failure message="assert 1 == 2">x</failure></testcase>
</testsuite></testsuites>"""
RECORD = {"project": "items-api", "acceptance_dir": "acceptance", "acceptance_pattern": "test_*.py",
          "acceptance_report": "test-results/acceptance.xml",
          "acceptance_test": [".venv/bin/python", "-m", "pytest", "acceptance", "-q", "--junitxml=test-results/acceptance.xml"]}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "items-api" / "acceptance").mkdir(parents=True)
    (tmp_path / "items-api" / "acceptance" / "test_ac1_ac9.py").write_text("def test_x(): pass  # AC-1, AC-9, AC-8\n")
    getattr(per_file, "forget_runs", lambda: None)()
    yield tmp_path
    getattr(per_file, "forget_runs", lambda: None)()


def _a_counting_run(root: Path):
    def run(argv, category, project):
        run.calls += 1
        path = root / "items-api" / "test-results" / "acceptance.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(REPORT)
        return {"returncode": "1", "stdout": "1 failed, 1 passed"}
    run.calls = 0
    return run


def test_the_same_file_of_the_same_product_is_run_once_and_judged_by_each_defect_s_criteria(workspace, monkeypatch):
    monkeypatch.setattr(unstable, "fingerprint", lambda root: "same-product")
    run = _a_counting_run(workspace)

    first = per_file.each_file(workspace, RECORD, run, naming={"AC-9"})
    second = per_file.each_file(workspace, RECORD, run, naming={"AC-8"})

    assert run.calls == 1
    assert [r["outcome"] for r in first] == ["finished"]
    assert [r["outcome"] for r in second] == ["failed"]


def test_a_changed_product_runs_the_file_again(workspace, monkeypatch):
    products = iter(["before", "after"])
    monkeypatch.setattr(unstable, "fingerprint", lambda root: next(products))
    run = _a_counting_run(workspace)

    per_file.each_file(workspace, RECORD, run, naming={"AC-9"})
    per_file.each_file(workspace, RECORD, run, naming={"AC-9"})

    assert run.calls == 2


def test_a_workspace_with_no_fingerprint_is_never_reused(workspace, monkeypatch):
    monkeypatch.setattr(unstable, "fingerprint", lambda root: "")
    run = _a_counting_run(workspace)

    per_file.each_file(workspace, RECORD, run, naming={"AC-9"})
    per_file.each_file(workspace, RECORD, run, naming={"AC-9"})

    assert run.calls == 2
