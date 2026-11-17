"""The metrics the worker records reach the endpoint the app serves.

Item 2 of plan-part3 wired `MetricsTracker`'s three recorders at the points that
know the answer. It did not cross the process boundary, and in this deployment
that boundary runs straight through the middle of the feature:

- `record_run` is called in `runner.start_run`, which runs in the **API**.
- `record_stage_duration` is called in the gate loop and
  `record_defect_resolution` in the sprint loop - both run in the **worker**.
- `/metrics` is served by the **API**.

Observed on 2026-09-21 against a live run several stages in: the endpoint served
`run_total 1.0` and a `stage_duration_seconds` histogram with no samples, and
`defects_resolved_total 0.0`. That is precisely the state §3.1 calls "worse than
no dashboard" - it reads as "nothing has ever worked" - arriving *after* the fix
that was supposed to prevent it.

`prometheus_client`'s multiprocess mode is the mechanism: both containers mount
the same `appdata` volume, and `prometheus_fastapi_instrumentator` builds a
`MultiProcessCollector` when `PROMETHEUS_MULTIPROC_DIR` is set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_it_is_a_no_op_without_the_variable(monkeypatch):
    """Single-process use - the CLI and these tests - must stay on the plain registry."""
    from app.observability.metrics import _prepare_multiprocess_dir

    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    _prepare_multiprocess_dir()  # must not raise


def test_it_creates_the_directory_when_set(tmp_path, monkeypatch):
    from app.observability.metrics import _prepare_multiprocess_dir

    target = tmp_path / "prom"
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(target))
    _prepare_multiprocess_dir()
    assert target.is_dir()


def test_an_unusable_directory_does_not_stop_the_process(monkeypatch):
    """A metrics problem must never be the reason a container will not start."""
    from app.observability.metrics import _prepare_multiprocess_dir

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "/proc/cannot/create/this")
    _prepare_multiprocess_dir()  # must not raise


def test_the_directory_is_not_wiped_on_startup(tmp_path, monkeypatch):
    """Counters are cumulative; a wipe would reset the totals being reported."""
    from prometheus_client import values
    from prometheus_client.mmap_dict import MmapedDict

    from app.observability.metrics import _prepare_multiprocess_dir

    monkeypatch.setattr(values, "ValueClass", values.ValueClass)  # put back what the start replaces
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    earlier = MmapedDict(str(tmp_path / "counter_4242.db"))
    earlier.write_value("runs_total", 7.0, 0.0)
    earlier.close()

    _prepare_multiprocess_dir()

    assert [value for _, value, _, _ in MmapedDict.read_all_values_from_file(str(tmp_path / "counter_4242.db"))] == [7.0]


def test_both_services_share_the_directory():
    """One service configured and not the other is half a fix."""
    import re

    compose = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    text = compose.read_text()
    assert "PROMETHEUS_MULTIPROC_DIR" in text

    # It must sit in the shared environment block, not under one service, so
    # that app and worker cannot drift apart.
    shared = text.split("services:")[0]
    assert "PROMETHEUS_MULTIPROC_DIR" in shared, (
        "the variable is set per-service; app and worker must share one directory"
    )


def test_the_shared_path_is_on_the_shared_volume():
    """`/app/data` is the mount both containers have; anywhere else is private."""
    compose = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    text = compose.read_text()
    line = next(l for l in text.splitlines() if "PROMETHEUS_MULTIPROC_DIR:" in l)
    assert "/app/data" in line, f"not on the shared volume: {line.strip()}"
