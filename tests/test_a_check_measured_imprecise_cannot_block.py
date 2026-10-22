"""A check measured under 90% precision is review-only (Initiative AO.5).

The checks that read the files decide whether a sprint's product is broken, and
some infer behaviour from patterns. A check's precision is now measured from the
scored benchmark runs - calling a product broken when every hidden test of it
passed is wrong - and one under 90% over five or more scored products can no
longer block: its findings are hints.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.analysis import integration_checks as ic

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "check_precision.py"


def _write(tmp_path, measured) -> None:
    (tmp_path / "loop").mkdir(exist_ok=True)
    (tmp_path / "loop" / "check_precision.json").write_text(json.dumps(measured))


def test_a_check_under_the_bar_over_enough_products_is_review_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write(tmp_path, {"some check": {"fired": 6, "false": 2, "precision": 0.667},
                      "a precise check": {"fired": 8, "false": 0, "precision": 1.0},
                      "a rarely seen check": {"fired": 2, "false": 2, "precision": 0.0}})

    imprecise = ic.checks_too_imprecise_to_block()

    assert imprecise == frozenset({"some check"})


def test_a_declared_breaking_check_measured_imprecise_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    name = next(iter(ic._FLOORS))
    _write(tmp_path, {name: {"fired": 5, "false": 3, "precision": 0.4}})

    assert ic._grade((name, None), "anything", False, ic.checks_too_imprecise_to_block()) == "hint"
    assert ic._grade((name, None), "anything", False) == ic._FLOORS[name]


def test_no_measurement_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert ic.checks_too_imprecise_to_block() == frozenset()


def test_the_script_measures_precision_against_the_hidden_tests(tmp_path):
    spec = importlib.util.spec_from_file_location("check_precision_ao5", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    (tmp_path / "run-a.json").write_text(json.dumps({"product": "/app/data/workspaces/default/workspace-run-a/app", "score": 1.0}))
    (tmp_path / "run-b.json").write_text(json.dumps({"product": "/app/data/workspaces/default/workspace-run-b/app", "score": 0.5}))

    scores = script.hidden_scores(tmp_path)
    measured = script.precision({"c": ["workspace-run-a", "workspace-run-b", "workspace-unscored"]}, scores)

    assert scores == {"workspace-run-a": 1.0, "workspace-run-b": 0.5}
    assert measured == {"c": {"fired": 2, "false": 1, "precision": 0.5}}


def test_a_check_about_the_tests_is_not_judged_by_the_hidden_tests(tmp_path):
    spec = importlib.util.spec_from_file_location("check_precision_ao5b", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    scores = {"workspace-run-a": 1.0}

    measured = script.precision({"test files against the project's own test command": ["workspace-run-a"],
                                 "the ids scripts reach for against the page": ["workspace-run-a"]}, scores)

    assert list(measured) == ["the ids scripts reach for against the page"]
