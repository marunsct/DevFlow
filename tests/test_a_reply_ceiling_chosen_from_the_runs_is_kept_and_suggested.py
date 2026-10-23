"""A reply ceiling chosen from what a model did on real runs outlives a new diagnosis, and the scan suggests one.

Measured on one model: 21 of 97 replies were over 16,000 tokens and held 73% of the output while the
median was 3,777; the diagnosis only sets a ceiling when a model loops, so a new diagnosis would have
dropped the ceiling the runs had shown it needs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.models import deep_diagnosis
from app.models.registry import merge_into_fitness

ROOT = Path(__file__).resolve().parent.parent


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name + "_t", ROOT / "scripts" / "loop" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.models.guidance.ensure_rows", lambda: None)


def _diagnosis(model="m1", ceiling=None):
    return deep_diagnosis.Diagnosis(model=model, measured_at="2026-10-24T00:00:00+00:00", baseline=(), reply_ceiling=ceiling)


def test_a_ceiling_from_the_runs_survives_a_new_diagnosis():
    merge_into_fitness("m1", {"deep_diagnosis": {"reply_ceiling": 24000, "reply_ceiling_from": "tail of a run"}})

    deep_diagnosis.keep(_diagnosis())

    kept = deep_diagnosis.recorded("m1")
    assert kept["reply_ceiling"] == 24000 and kept["reply_ceiling_from"] == "tail of a run"


def test_a_ceiling_the_diagnosis_set_is_replaced_by_the_next_diagnosis():
    deep_diagnosis.keep(_diagnosis(ceiling=40000))
    deep_diagnosis.keep(_diagnosis())

    assert deep_diagnosis.recorded("m1")["reply_ceiling"] is None


def test_the_ceiling_command_sets_and_clears_it():
    deep_diagnosis.keep(_diagnosis())
    command = _script("set_ceiling")

    command.set_ceiling("m1", 24000, "why")
    assert deep_diagnosis.recorded("m1")["reply_ceiling"] == 24000
    deep_diagnosis.keep(_diagnosis())
    assert deep_diagnosis.recorded("m1")["reply_ceiling"] == 24000

    command.set_ceiling("m1", None)
    assert deep_diagnosis.recorded("m1")["reply_ceiling"] is None
    deep_diagnosis.keep(_diagnosis())
    assert deep_diagnosis.recorded("m1")["reply_ceiling"] is None


def test_the_scan_suggests_a_ceiling_for_a_heavy_tail_and_not_for_a_light_one():
    scan = _script("scan")
    heavy = [3000] * 76 + [30000] * 21
    light = [3000] * 90 + [17000] * 3

    line = scan.ceiling_suggestion(heavy)
    assert line.startswith("REPLY CEILING: 21 of 97 replies are over 16,000 tokens") and "loop.sh ceiling 24,000" not in line
    assert scan.ceiling_suggestion(light) == ""
    assert scan.ceiling_suggestion([30000] * 5) == ""
