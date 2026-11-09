"""The harness runs the product's unit tests once while the product is unchanged (behind `MEASURE_ONCE`).

Measured on one run: in one test round, with no fix between, the harness ran the same `npm test` four times; a unit
test never settled, and each run took the sandbox's full five minutes - twenty minutes on one unchanged product.
The suite already kept its last run while the product's fingerprint stood; the unit run now does the same.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.graph import workflow


def _project(tmp_path, monkeypatch, fingerprint):
    (tmp_path / ".harness").mkdir()
    monkeypatch.setenv("MEASURE_ONCE", "on")
    monkeypatch.setattr("app.stacks.contract.read", lambda root: {"project": "notes-api", "unit_test": ["npm", "test"]})
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: None)
    monkeypatch.setattr("app.acceptance.unstable.fingerprint", lambda root: fingerprint["now"])
    runs = []
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner",
                        lambda root: lambda argv, category, project: runs.append(argv) or {"returncode": 1, "stdout": "fail 1"})
    return runs


def test_an_unchanged_product_is_not_run_again_and_a_changed_one_is(tmp_path, monkeypatch):
    fingerprint = {"now": "a"}
    runs = _project(tmp_path, monkeypatch, fingerprint)

    first = workflow._run_unit_tests_procedurally(str(tmp_path))
    second = workflow._run_unit_tests_procedurally(str(tmp_path))
    fingerprint["now"] = "b"
    third = workflow._run_unit_tests_procedurally(str(tmp_path))

    assert len(runs) == 2, "run, kept, run again after a change"
    assert first[0] is False and second == first and third[0] is False


def test_off_every_call_runs(tmp_path, monkeypatch):
    runs = _project(tmp_path, monkeypatch, {"now": "a"})
    monkeypatch.setenv("MEASURE_ONCE", "off")

    workflow._run_unit_tests_procedurally(str(tmp_path))
    workflow._run_unit_tests_procedurally(str(tmp_path))

    assert len(runs) == 2
