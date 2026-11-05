"""A request cut short because the run was paused is not counted as a model error.

Measured on one run: 14 of its 15 "model errors" were requests a deploy's pause cancelled, and the score flagged a
regression of model errors against a mean under one.
"""
from app.observability import run_kpis

ROWS = [
    {"kind": "model_request", "stage": "consult", "at": "2026-01-01T00:00:00+00:00"},
    {"kind": "model_error", "stage": "consult", "at": "2026-01-01T00:00:05+00:00",
     "error": "RunCancelled: Run run-x was paused"},
    {"kind": "model_request", "stage": "consult", "at": "2026-01-01T00:01:00+00:00"},
    {"kind": "model_error", "stage": "consult", "at": "2026-01-01T00:01:05+00:00",
     "error": "OpenAIAPIError: Error code: 500"},
]


def test_only_the_server_s_failure_counts():
    assert run_kpis.kpis(ROWS)["model_errors"] == 1
