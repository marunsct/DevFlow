"""Whether the runs after a change got better or worse, each against its own family before it.

Families differ several times over in size, so a change followed by a larger family would look like
a regression if runs were compared across families.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "loop"
spec = importlib.util.spec_from_file_location("impact", SCRIPTS / "impact.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)

POSITION = {"old": 0, "new": 1}


def _row(commit, family, wall, rounds, score="1.0"):
    return {"harness_commits": commit, "benchmark": family, "active_minutes": str(wall), "test_rounds": str(rounds),
            "hidden_score": score, "defect_fix_stages": "4", "defects_fixed": "2"}


def test_a_kpi_that_rose_within_its_family_is_worse():
    rows = [_row("old", "small", 40, 2), _row("old", "large", 200, 3),
            _row("new", "small", 40, 4), _row("new", "large", 200, 6)]
    report = impact.compare(rows, 1, POSITION)
    assert report["kpis"]["test_rounds"]["worse"] and report["kpis"]["test_rounds"]["ratio"] == 2.0
    assert not report["kpis"]["active_minutes"]["worse"]


def test_a_larger_family_after_the_change_is_not_a_regression():
    rows = [_row("old", "small", 40, 2), _row("old", "large", 200, 3), _row("new", "large", 200, 3)]
    assert not impact.compare(rows, 1, POSITION)["kpis"]["active_minutes"]["worse"]


def test_a_lost_hidden_test_is_worse():
    rows = [_row("old", "small", 40, 2), _row("new", "small", 40, 2, score="0.9")]
    assert impact.compare(rows, 1, POSITION)["kpis"]["hidden_score"]["worse"]


def test_a_run_on_both_versions_counts_after_the_change():
    assert impact.finished_on({"harness_commits": "old new"}, POSITION) == 1
    assert impact.finished_on({"harness_commits": "unknown"}, POSITION) is None


def test_one_run_after_a_change_is_a_watch_not_a_regression():
    """Measured: seven changes in a row were each "worse" on wall time x13 from the one run after them, whose wall
    held a nine-hour pause for a host restart."""
    rows = [_row("old", "small", 40, 2), _row("old", "small", 44, 2), _row("new", "small", 400, 6)]
    report = impact.compare(rows, 1, POSITION)
    assert not report["kpis"]["test_rounds"]["worse"] and report["kpis"]["test_rounds"]["watch"]
    rows += [_row("new", "small", 400, 6)]
    assert impact.compare(rows, 1, POSITION)["kpis"]["test_rounds"]["worse"]


def test_wall_time_with_its_pauses_is_not_read():
    assert "wall_minutes" not in dict(impact.KPIS)
