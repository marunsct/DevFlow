"""The benchmark's mutation probe also says which changes the unit tests caught, and a score with them.

Measured on one run: mutation-guided tests (QM.2) had the testing role write three unit tests, each proven to fail
with its change, and the run's mutation score still read 0.583 - it counted only the locked acceptance suite. The
suite-only `score` stays as it was, for comparison across runs; `score_with_unit_tests` counts both.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _mutate_module():
    spec = importlib.util.spec_from_file_location("bench_mutate", ROOT / "scripts" / "bench" / "mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(*names):
    return SimpleNamespace(report=SimpleNamespace(tests=[SimpleNamespace(name=n, outcome="passed") for n in names]))


def test_a_change_only_the_unit_tests_catch_counts_in_the_score_with_them(tmp_path, monkeypatch):
    mutate = _mutate_module()
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "a.ts").write_text("x")
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: None)
    monkeypatch.setattr("app.acceptance.suite.location", lambda root: ("",))
    monkeypatch.setattr(mutate, "sites", lambda files, project: [{"file": "a.ts"}, {"file": "a.ts"}])
    monkeypatch.setattr(mutate, "spread", lambda found, count: found)
    monkeypatch.setattr(mutate, "source_files", lambda project, kept: [])
    applied = []
    monkeypatch.setattr(mutate, "apply", lambda project, site: applied.append(site) or b"x")
    monkeypatch.setattr("app.acceptance.suite.run", lambda root, save=False: _result("[AC-1] adds"))
    unit_runs = iter([{"u1", "u2"}, {"u1"}, {"u1", "u2"}])
    monkeypatch.setattr("app.acceptance.mutation_guided._run_the_unit_tests", lambda root: next(unit_runs))

    result = mutate.mutate(tmp_path / "ws", tmp_path / "out.json", 2)

    assert result["score"] == 0.0, "the suite noticed neither change"
    assert result["caught_with_unit_tests"] == 1 and result["score_with_unit_tests"] == 0.5
    assert json.loads((tmp_path / "out.json").read_text())["score_with_unit_tests"] == 0.5
