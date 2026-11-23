"""docs/measuring.md has one generated row per switch, with its runs on and off and a verdict only on both sides.

Hand-kept, the register named 5 of 58 switches; the rest sat in group rows reading "see `loop.sh switches`".
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("switch_register", ROOT / "scripts" / "loop" / "switch_register.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(on, fired=(), score=1.0, minutes=30.0):
    return {"on": set(on), "fired": set(fired), "score": score, "minutes": minutes}


def test_off_counts_only_after_the_switch_first_ran_and_a_verdict_needs_both_sides():
    register = _module()
    runs = [_run([], score=0.0), _run(["A"], ["A"]), _run([], score=0.5), _run(["A"]), _run([], score=0.5)]
    row = register.rows({"A": ("Efficiency", False), "B": ("Efficiency", False)}, runs)
    assert row[0] == "| `A` | Efficiency | off | 2 | no signal | 2 | measured: hidden 1.00 on / 0.50 off; minutes 30.00 / 30.00 |"
    assert "| 0 | no signal | 0 | not measured: needs 2 more on and 2 more off |" in row[1]


def test_every_switch_of_the_code_has_a_row():
    register = _module()
    names = register._the_switches()
    block = "\n".join(register.render(names, []))
    assert all(f"| `{name}` |" in block for name in names)
    # 58 once; 13 measured checks became built-in fixes on 11-16 (LR.65), and built-in fixes are not switches.
    assert len(names) >= 45


def test_loop_sh_writes_it():
    assert 'measuring) shift; "$PY" "$HERE/switch_register.py"' in (ROOT / "scripts" / "loop" / "loop.sh").read_text()


def test_a_switch_with_a_signal_counts_its_firings(monkeypatch):
    register = _module()
    monkeypatch.setattr(register, "_signalled", lambda: {"A"})
    runs = [_run(["A"], ["A"]), _run(["A"])]
    assert register.rows({"A": ("Efficiency", True)}, runs)[0].startswith("| `A` | Efficiency | on | 2 | 1 | 0 |")


def test_only_benchmark_family_runs_are_counted_not_a_brief_started_by_hand(tmp_path):
    """Owner 2026-11-23: the medium and high briefs run by hand are not counted in the measuring."""
    register = _module()
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("run,benchmark,switches_on,switches_fired,active_minutes\n"
                      "run-a,notes-api,A,,30\nrun-b,,A,,300\nrun-c,a-medium-brief,A,,200\n")
    bench = tmp_path / "bench"
    bench.mkdir()
    for run in ("run-a", "run-b", "run-c"):
        (bench / f"{run}.json").write_text('{"score": 1.0}')
    runs = register._runs(ledger, bench, families={"notes-api", "tasks-api"})
    assert [r["minutes"] for r in runs] == [30.0]
    assert "notes-api" in register._families() and "tasks-api" in register._families()
