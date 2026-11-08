"""A harness finding's revision guard uses the run's own revision limit (harness review HR2.D.4).

The guards compared with the full limit (6) while fast delivery escalates at two, so a harness finding first raised
on fast delivery's last revision passed its guard and escalated unrevised.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.graph import workflow


def test_in_fast_delivery_the_last_revision_raises_no_new_harness_finding(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: True)
    state = {"architecture_revision_count": 1,
             "product_intake": SimpleNamespace(success_measures=["A person can export every note as a file"])}
    assert workflow._a_success_measure_the_specification_drops(state, "A notes service.") is None


def test_the_full_limit_still_holds_outside_fast_delivery(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: False)
    assert workflow._the_revision_limit() == workflow.MAX_ARCHITECTURE_REVISIONS


def test_no_guard_compares_with_the_full_limit_directly() -> None:
    source = inspect.getsource(workflow)
    assert 'architecture_revision_count", 0) + 1 >= MAX_ARCHITECTURE_REVISIONS' not in source
    assert "limit = _the_revision_limit()" in source
