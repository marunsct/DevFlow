"""A mutant that turns every test red is inconclusive, not caught (HR2.Q.6a).

Measured over 2,247 stored mutants: 334 (15%) broke the product outright and counted as caught, inflating the
mutation score the RC rule and the impact report now read.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bench" / "mutate.py"


def _scored():
    spec = importlib.util.spec_from_file_location("mutate_q6a", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # the script's imports need the app; the function is self-contained
        pass
    return module.scored


def test_a_product_breaking_mutant_is_left_out_of_the_score():
    mutants = [
        {"caught": True, "everything_failed": True},
        {"caught": True, "everything_failed": False},
        {"caught": False, "everything_failed": False},
    ]
    out = _scored()(mutants)
    assert out["inconclusive"] == 1 and out["score"] == 0.5 and out["score_with_breaks"] == 0.667


def test_only_breaking_mutants_score_nothing():
    assert _scored()([{"caught": True, "everything_failed": True}])["score"] is None
