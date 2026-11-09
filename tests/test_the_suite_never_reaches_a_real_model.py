"""The test suite's model address is one that refuses, whatever the operator's `.env` names.

Measured: with `.env` naming a model server that needs no key, a test of the run's startup path sent real requests to
that server, beside the live runs, took minutes, and crashed its test worker.
"""
from __future__ import annotations

from app.config import load_settings


def test_the_settings_the_suite_sees_name_no_real_server():
    assert (load_settings().openai_base_url or "").rstrip("/") == "http://127.0.0.1:9/v1"
