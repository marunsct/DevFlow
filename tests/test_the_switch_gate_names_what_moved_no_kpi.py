"""`loop.sh effects gate`: switches on, the runs each acted in, KPI movement against the off arm, candidates to park (plan item 22)."""
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = runpy.run_path(str(ROOT / "scripts" / "loop" / "switch_gate.py"))


def _run(on: str, minutes: float, *, fired: str | None = "none", benchmark: str = "b", hidden: float = 1.0, mixed: bool = False,
         model: str = "") -> dict:
    row = {"run": "r", "benchmark": benchmark, "switches_on": on, "active_minutes": str(minutes),
           "hidden_score": str(hidden), "mixed_versions": str(mixed), "served_model": model}
    if fired is not None:
        row["switches_fired"] = fired
    return row


def _by_name(rows, signals=frozenset({"A"}), minimum=3):
    return {r.name: r for r in GATE["reports"](rows, signals, minimum)}


def test_a_switch_that_acted_and_moved_nothing_is_a_candidate():
    rows = [_run("A", 50, fired="A"), _run("A", 51, fired="A"), _run("A", 49, fired="A"),
            _run("Z", 48), _run("Z", 52)]
    report = _by_name(rows)["A"]
    assert (report.runs_on, report.runs_off, report.runs_fired) == (3, 2, 3)
    assert report.verdict == "PARK CANDIDATE: acted in 3 runs and moved no KPI"


def test_a_switch_that_never_acted_is_told_apart_from_one_that_acted():
    rows = [_run("A", 50), _run("A", 51), _run("A", 49), _run("Z", 48), _run("Z", 52)]
    assert _by_name(rows)["A"].verdict == "PARK CANDIDATE: never acted in 3 runs"


def test_a_switch_with_no_signal_is_not_called_idle():
    rows = [_run("Q", 50), _run("Q", 51), _run("Q", 49), _run("Z", 48), _run("Z", 52)]
    assert "whether it acted is unknown" in _by_name(rows)["Q"].verdict


def test_runs_before_the_firing_column_are_not_counted_as_never_acting():
    rows = [_run("A", 50, fired=None), _run("A", 51, fired=None), _run("A", 49, fired=""), _run("Z", 48, fired=None),
            _run("Z", 52, fired=None)]
    report = _by_name(rows)["A"]
    assert report.runs_with_a_firing_record == 0
    assert "too few runs recorded" in report.verdict


def test_movement_past_the_off_arm_s_whole_range_keeps_the_switch_and_spread_does_not():
    moved = [_run("A", 30, fired="A"), _run("A", 32, fired="A"), _run("A", 31, fired="A"), _run("Z", 50), _run("Z", 60)]
    report = _by_name(moved)["A"]
    assert report.verdict == "keep: moved a KPI"
    assert report.moved["b:active_minutes"] == "better 55 -> 31"
    # Inside what the off arm did by itself: not movement, however far from its mean.
    inside = [_run("A", 40, fired="A"), _run("A", 40, fired="A"), _run("A", 40, fired="A"), _run("Z", 20), _run("Z", 60)]
    assert _by_name(inside)["A"].moved == {}


def test_a_switch_that_only_made_things_worse_is_named():
    rows = [_run("A", 90, fired="A", hidden=0.5), _run("A", 95, fired="A", hidden=0.5), _run("A", 92, fired="A", hidden=0.5),
            _run("Z", 50), _run("Z", 52)]
    assert _by_name(rows)["A"].verdict == "PARK CANDIDATE: only made KPIs worse"


def test_arms_compare_within_one_benchmark_and_never_a_mixed_run():
    # The off arm is another family, three times as long: nothing can be said.
    across = [_run("A", 30, benchmark="small"), _run("A", 30, benchmark="small"), _run("A", 30, benchmark="small"),
              _run("Z", 100, benchmark="large"), _run("Z", 100, benchmark="large")]
    assert _by_name(across)["A"].moved == {}
    # The off runs are mixed: no off arm.
    mixed = [_run("A", 30), _run("A", 30), _run("A", 30), _run("Z", 100, mixed=True), _run("Z", 100, mixed=True)]
    assert _by_name(mixed)["A"].verdict == "no off arm to compare with"
    # The off arm ran on another model: every switch turned on after a model change read as making things worse.
    model = [_run("A", 30, model="m2"), _run("A", 30, model="m2"), _run("A", 30, model="m2"),
             _run("Z", 100, model="m1"), _run("Z", 100, model="m1")]
    assert _by_name(model)["A"].verdict == "no off arm to compare with"


def test_a_built_in_fix_is_no_switch_to_park():
    rows = [_run("A", 50), _run("A", 51), _run("A", 49), _run("Z", 48), _run("Z", 52)]
    assert "A" not in {r.name for r in GATE["reports"](rows, frozenset(), 3, frozenset({"A"}))}


def test_too_few_runs_is_no_candidate_and_switches_always_together_say_so():
    rows = [_run("A B", 50), _run("A B", 50), _run("Z", 50), _run("Z", 50)]
    report = _by_name(rows)["A"]
    assert report.verdict.startswith("too few runs")
    assert report.together_with == ["B"]
    assert "always on together" in "\n".join(GATE["lines"](rows, frozenset({"A"}), 3))


def test_fix_rows_naming_no_test_are_counted():
    plan = "| LF.1 | seen | changed | `tests/test_x.py` |\n| LF.2 | seen | changed | none |\n| LF.3 | a | b | test_y |\n"
    assert GATE["rows_without_a_predicted_flip"](plan) == ["LF.2"]


def test_the_report_changes_nothing_it_is_only_told(tmp_path, capsys):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("run,benchmark,switches_on,active_minutes,mixed_versions\nr,b,A,5,False\n")
    before = ledger.read_bytes()
    assert GATE["main"](str(ledger), "3", "") == 0
    assert "changes no switch" in capsys.readouterr().out
    assert ledger.read_bytes() == before


def test_loop_sh_routes_the_gate_to_the_report():
    text = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    assert 'switch_gate.py" data/kpi/ledger.csv' in text


def test_the_kpi_row_records_which_switches_acted():
    from app.observability.switch_firing import fired

    records = [
        {"kind": "model_request", "messages": [{"content": "You have sent x 3 times, and no file has changed since the first."}]},
        {"kind": "tool_result", "content": "...Your defect is fixed"},
        {"kind": "model_response", "text": "Where things stand"},  # a model's own words are not the switch acting
        "not a record",
    ]
    assert fired(records) == ["AGENT_LOOP_FIX_LIMITS", "VERIFY_AFTER_WRITE"]
    assert '"switches_fired"' in (ROOT / "scripts" / "loop" / "kpi.py").read_text()
