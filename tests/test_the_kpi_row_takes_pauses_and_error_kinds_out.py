"""A run's KPI row takes its recorded pauses off `active_minutes` and counts model errors by kind (HR2.R.1, R.4).

Measured: 150 paused minutes on one day sat inside `active_minutes`; the owner's model unloads and quota counted as
the harness's errors and were flagged as regressions.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "kpi.py"
spec = importlib.util.spec_from_file_location("kpi_script", SCRIPT)
kpi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kpi)


def test_pauses_come_off_the_active_minutes_and_are_kept_apart():
    out = kpi.with_the_pauses({"active_minutes": 60.0, "wall_minutes": 61.0}, 300)
    assert out["active_minutes"] == 55.0 and out["paused_minutes"] == 5.0 and out["wall_minutes"] == 61.0
    assert kpi.with_the_pauses({"active_minutes": 2.0}, 900)["active_minutes"] == 0.0


def test_only_a_rejected_request_counts_as_a_model_error():
    records = [
        {"kind": "model_error", "error": "RunCancelled: Run x was stopped; this stage's call is not made."},
        {"kind": "model_error", "error": "APIError: No model loaded"},
        {"kind": "model_error", "error": "OpenAIConnectionError: Lost connection to the server"},
        {"kind": "model_error", "error": "ReadTimeout: request timed out"},
        {"kind": "model_error", "error": "BadRequestError: 400 the request's tool choice is not supported"},
    ]
    out = kpi.with_model_errors_by_kind({"model_errors": 5}, records)
    assert out["model_errors"] == 1
    assert (out["model_errors_owner_action"], out["model_errors_server_unavailable"], out["model_errors_timeout"]) == (1, 1, 1)
