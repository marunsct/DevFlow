"""A run that did not finish hands over its best attempt, said with what it passed.

Deep review 2026-11-18, item F4a: the product download was offered only on a completed run, though a stopped or
cancelled run keeps a record of its best attempt; a run cancelled mid-round can hold a worse product than that best.
"""
from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.acceptance import suite
from app.graph import best_attempt
from app.sprint import product_archive


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("KEEP_THE_BEST_ATTEMPT", "on")
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: None)


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("WORKING = True\n")
    return tmp_path


def _measured(monkeypatch, passed: int, of: int = 10, criteria: dict | None = None):
    monkeypatch.setattr(suite, "last_result", lambda repo: {
        "ran": True, "passed": passed, "failed": of - passed, "criteria": criteria or {}})


def _archive(root: Path, finished: bool) -> zipfile.ZipFile:
    holds = product_archive.what_it_holds(root, finished=finished)
    return zipfile.ZipFile(io.BytesIO(product_archive.build(root, "run-1", at_commit=holds["commit"])))


def test_a_cancelled_run_worse_than_its_best_hands_over_the_best_files(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, 8)
    best_attempt.note(root)
    (root / "src" / "app.py").write_text("WORKING = False  # a redraft broke it\n")
    _measured(monkeypatch, 2)

    holds = product_archive.what_it_holds(root, finished=False)
    archive = _archive(root, finished=False)

    assert (holds["version"], holds["tests_passed"], holds["tests_total"]) == ("best", 8, 10)
    assert archive.read("run-1/src/app.py").decode() == "WORKING = True\n"
    assert not [name for name in archive.namelist() if "/.git/" in name or "/.harness/" in name]


def test_a_finished_run_hands_over_the_product_as_it_stands(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, 8)
    best_attempt.note(root)
    (root / "src" / "app.py").write_text("WORKING = 'changed after the best'\n")
    _measured(monkeypatch, 2)

    archive = _archive(root, finished=True)

    assert product_archive.what_it_holds(root, finished=True)["version"] == "latest"
    assert archive.read("run-1/src/app.py").decode() == "WORKING = 'changed after the best'\n"


def test_a_stopped_run_already_at_its_best_says_how_many_criteria_it_passed(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    criteria = {"AC-1": {"status": "passed"}, "AC-2": {"status": "passed"}, "AC-3": {"status": "failed"}}
    _measured(monkeypatch, 8, criteria=criteria)
    best_attempt.note(root)

    holds = product_archive.what_it_holds(root, finished=False)

    assert (holds["version"], holds["commit"], holds["criteria_passed"], holds["criteria_total"]) == ("best", "", 2, 3)
    assert _archive(root, finished=False).read("run-1/src/app.py").decode() == "WORKING = True\n"
