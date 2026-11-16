"""Every benchmark has a quality set, and the scorer runs it whatever the runner (LR.25).

Found in the launch review: the hidden tests say whether a product does what its brief says, and on a benchmark every
run now passes they no longer tell one product from a better one. The quality sets found shipped products losing
parallel writes and taking bad input; but the scorer skipped every playwright quality set, and the browser families
and the change family had none.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCHES = sorted(p for p in (ROOT / "benchmarks").iterdir() if (p / "bench.json").is_file())


def _score_module():
    spec = importlib.util.spec_from_file_location("bench_score", ROOT / "scripts" / "bench" / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("bench", BENCHES, ids=lambda p: p.name)
def test_the_benchmark_has_a_quality_set(bench: Path) -> None:
    runner = json.loads((bench / "bench.json").read_text())["runner"]
    pattern = "*.spec.mjs" if runner == "playwright" else "test_*.py"
    assert list((bench / "quality").glob(pattern)), f"{bench.name} has no quality tests for its {runner} runner"


def test_a_playwright_quality_set_is_run_against_a_server_of_its_own(tmp_path, monkeypatch) -> None:
    score = _score_module()
    bench = tmp_path / "bench"
    (bench / "quality").mkdir(parents=True)
    (bench / "quality" / "edges.spec.mjs").write_text("// a spec\n")
    work = tmp_path / "work"
    (work / "product").mkdir(parents=True)
    calls = []

    def ran(work_, specs, report, kind, target, data_dir, notes):
        calls.append((specs.name, kind, target, data_dir))
        report.write_text('<testsuite><testcase name="an edge"/></testsuite>')
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(score, "_playwright", ran, raising=False)
    found = score._the_quality_set(bench, work, "playwright", {}, [], "browser_app")
    assert found == [{"name": "an edge", "outcome": "passed", "message": ""}]
    assert calls and calls[0][0] == "quality" and calls[0][3] != work / "data"
