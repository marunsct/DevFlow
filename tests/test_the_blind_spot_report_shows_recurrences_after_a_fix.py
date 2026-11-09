"""`loop.sh blind-spots` shows each hidden test that keeps failing, and failures after the fix that named it (HR2.Q.11)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "blind_spots.py"
    spec = importlib.util.spec_from_file_location("loop_blind_spots", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scored(bench: Path, run: str, score: float, failed: list[str], at: float) -> None:
    path = bench / f"{run}.json"
    path.write_text(json.dumps({"benchmark": "notes-api", "score": score, "tests": [
        {"name": name, "outcome": "failed"} for name in failed]}))
    os.utime(path, (at, at))


def test_a_failure_after_the_row_that_named_it_is_a_recurrence(tmp_path) -> None:
    blind = _module()
    _scored(tmp_path, "run-a", 0.8, ["test_refuses_an_update_that_empties_the_title"], 1_000)
    _scored(tmp_path, "run-b", 0.9, ["test_refuses_an_update_that_empties_the_title"], 3_000)
    _scored(tmp_path, "run-c", 0.0, ["test_creates_a_note"], 3_000)
    plan = tmp_path / "plan.md"
    plan.write_text("| LF.9 | an update that empties the title was accepted | probe | refuses an update that empties the title |\n")

    found = blind.failures(tmp_path)
    assert [(f[1], f[3]) for f in found] == [("test_refuses_an_update_that_empties_the_title", "run-a"),
                                             ("test_refuses_an_update_that_empties_the_title", "run-b")], \
        "a run whose every test failed is left out"
    named = blind.rows_naming(["test_refuses_an_update_that_empties_the_title"], plan)
    assert named == {"test_refuses_an_update_that_empties_the_title": "LF.9"}
    lines = blind.report(found, named, {"LF.9": 2_000})
    assert "named by LF.9; failed 1 time(s) since (last run-b)" in lines[1]
    assert lines[1].lstrip().startswith("2 failed")


def test_a_test_no_row_names_is_an_open_blind_spot(tmp_path) -> None:
    blind = _module()
    _scored(tmp_path, "run-a", 0.5, ["test_lists_every_note"], 1_000)
    lines = blind.report(blind.failures(tmp_path), {}, {})
    assert "no plan row names it - an open blind spot" in lines[1]


def test_a_run_scored_again_later_counts_by_the_code_it_ran_not_when_it_was_scored(monkeypatch) -> None:
    blind = _module()
    monkeypatch.setattr(blind, "RUN_COMMITS", {"run-old": "aaa"})
    monkeypatch.setattr(blind, "ROW_COMMITS", {"LF.9": "fff"})
    monkeypatch.setattr(blind, "ran_with", lambda run_commit, fix_commit: False)
    assert blind._after("run-old", 9_999, "LF.9", {"LF.9": 1_000}) is False
