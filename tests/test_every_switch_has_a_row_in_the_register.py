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
    assert row[0] == "| `A` | Efficiency | off | 2 | 1 | 2 | measured: hidden 1.00 on / 0.50 off; minutes 30.00 / 30.00 |"
    assert "| 0 | 0 | 0 | not measured: needs 2 more on and 2 more off |" in row[1]


def test_every_switch_of_the_code_has_a_row():
    register = _module()
    names = register._the_switches()
    block = "\n".join(register.render(names, []))
    assert all(f"| `{name}` |" in block for name in names)
    assert len(names) >= 58


def test_loop_sh_writes_it():
    assert 'measuring) shift; "$PY" "$HERE/switch_register.py"' in (ROOT / "scripts" / "loop" / "loop.sh").read_text()
