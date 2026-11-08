"""Each completion-gap kind is printed with how often it preceded a lost hidden test (harness review HR2.G.3)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "gap_precision.py"
    spec = importlib.util.spec_from_file_location("loop_gap_precision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_fixture_bench_directory_yields_the_table(tmp_path) -> None:
    gaps = _module()
    for n, (score, carried) in enumerate([
        (1.0, ["3 line(s) of the interface contract were not checked at release"]),
        (0.5, ["7 line(s) of the interface contract were not checked at release", "At release the product does not start"]),
        (0.8, ["2 line(s) of the interface contract were not checked at release"]),
        (1.0, []),
    ]):
        (tmp_path / f"run-{n}.json").write_text(json.dumps({"score": score, "completion_gaps": carried}))

    precision, base, runs = gaps.table(tmp_path)

    assert runs == 4 and base == 0.5
    assert precision["N line(s) of the interface contract"] == (2, 3)
    assert precision["At release the product does not"] == (1, 1)
    lines = gaps.lines_for(["9 line(s) of the interface contract were not checked", "At release the product does not start"],
                           precision, base)
    assert lines[0] == "gap kinds (runs that lost a hidden test: 50% of all scored runs):"
    assert lines[1].endswith("preceded a lost hidden test in 2 of 3 runs (67%)")
    assert lines[2].endswith("too few runs to say (1)")
