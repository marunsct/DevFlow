"""Finished runs show their time and score side by side, and forecast what the next one takes."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.server import outcomes


def _run(run_id, status, mode, hours, local=False):
    return SimpleNamespace(
        run_id=run_id, status=status, delivery_mode=mode, local_only=local,
        created_at="2026-10-15T00:00:00+00:00", updated_at=f"2026-10-15T{hours:02d}:00:00+00:00",
    )


RUNS = [
    _run("run-a", "completed", "fast", 12), _run("run-b", "completed", "fast", 6),
    _run("run-c", "completed", "fast", 9), _run("run-d", "failed", "fast", 2),
    _run("run-e", "completed", "thorough", 20), _run("run-f", "running", "fast", 1),
]


def test_each_finished_run_shows_how_it_ended_its_hours_and_its_score(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_OUTCOMES_DIR", str(tmp_path))
    (tmp_path / "run-a.json").write_text(json.dumps({"benchmark": "notes", "passed": 9, "total": 9, "score": 1.0, "tests": ["x"]}))

    rows = outcomes.outcomes(RUNS)

    assert [row["run_id"] for row in rows] == ["run-a", "run-b", "run-c", "run-d", "run-e"]
    assert rows[0]["hours"] == 12 and rows[0]["score"] == {"benchmark": "notes", "passed": 9, "total": 9, "score": 1.0}
    assert rows[1]["score"] is None


def test_a_completed_run_s_gaps_ride_the_outcome_row():
    """What the release knew it did not prove shows beside the score, so a
    'completed' run whose product fails its hidden tests is seen to have said
    so - or to have claimed verified when it was not (Initiative J.4)."""
    gapped = SimpleNamespace(
        run_id="run-g", status="completed", delivery_mode="fast", local_only=False,
        completion_gaps=["AC-2 ships deferred, unproven by the suite: no automated check"],
        created_at="2026-10-15T00:00:00+00:00", updated_at="2026-10-15T05:00:00+00:00",
    )

    rows = outcomes.outcomes([gapped, _run("run-h", "completed", "fast", 3)])

    assert rows[0]["completion_gaps"] == ["AC-2 ships deferred, unproven by the suite: no automated check"]
    assert rows[1]["completion_gaps"] == []


def test_the_forecast_is_the_typical_completed_run_of_that_mode_and_none_with_too_few():
    rows = outcomes.outcomes(RUNS)

    fast = outcomes.forecast(rows, "fast")
    assert {k: fast[k] for k in ("delivery_mode", "typical_hours", "shortest_hours", "longest_hours", "runs")} == {
        "delivery_mode": "fast", "typical_hours": 9.0, "shortest_hours": 6.0, "longest_hours": 12.0, "runs": 3,
    }
    # One thorough run: how many there were, and no time made of it.
    assert outcomes.forecast(rows, "thorough")["typical_hours"] is None
    assert outcomes.forecast(rows, "thorough")["runs"] == 1
    assert outcomes.forecast(rows, "other") is None


def test_the_route_is_reached_before_a_run_id_would_take_it():
    import inspect

    from app.server import runs

    source = inspect.getsource(runs)
    assert source.index('@runs.get("/outcomes")') < source.index('@runs.get("/{run_id}", response_model')


def _row(mode, hours, criteria, status="completed"):
    return {"status": status, "delivery_mode": mode, "hours": hours, "criteria": criteria}


def test_two_runs_are_too_few_to_call_a_time_typical():
    """Measured live: two thorough runs - a small benchmark and the low brief - made a
    "typical" 1.5 h beside a fast 4.7 h from larger briefs, so thorough read as faster."""
    rows = [_row("thorough", 0.77, 18), _row("thorough", 2.27, 8)]

    found = outcomes.forecast(rows, "thorough")

    assert found["runs"] == 2 and found["typical_hours"] is None and found["hours_per_criterion"] is None


def test_the_time_per_criterion_compares_briefs_of_different_sizes():
    rows = [_row("fast", 1.0, 8), _row("fast", 4.0, 16), _row("fast", 9.0, 18), _row("fast", 2.0, 10)]

    found = outcomes.forecast(rows, "fast")

    assert found["hours_per_criterion"] == round(sorted([1 / 8, 4 / 16, 9 / 18, 2 / 10])[1:3][0] / 2 + sorted([1 / 8, 4 / 16, 9 / 18, 2 / 10])[1:3][1] / 2, 3)
    assert (found["fewest_criteria"], found["most_criteria"]) == (8, 18)


def test_only_the_most_recent_runs_count():
    rows = [_row("fast", 1.0, 10)] * outcomes.RECENT_RUNS + [_row("fast", 50.0, 10)] * 5

    found = outcomes.forecast(rows, "fast")

    assert found["runs"] == outcomes.RECENT_RUNS and found["longest_hours"] == 1.0
