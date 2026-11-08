"""A suite reopened after the build that runs out of repair rounds keeps the suite as last locked; it fails no run.

Measured on one run: a locked test was skipped by the product's own `conftest.py`, the reopened suite went five
rounds proving nothing for it, and the run failed - its product passed every hidden test and never released.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest import mock

from app.graph import acceptance_nodes
from app.acceptance import suite


def _kept(state, repairing=True):
    with mock.patch.object(suite, "is_being_repaired", return_value=repairing), \
         mock.patch.object(suite, "put_back_the_suite_before_the_repair", return_value=["acceptance/test_a.py is back"]) as back, \
         mock.patch.object(suite, "lock") as lock, \
         mock.patch.object(suite, "run", return_value=SimpleNamespace(as_dict=lambda: {"passed": 22})):
        out = acceptance_nodes._kept_as_locked_before(state, "/w", "the repaired suite proves nothing: x is skipped")
    return out, back, lock


def test_a_repair_goes_back_where_it_came_from_with_the_gap():
    out, back, lock = _kept({"acceptance_return_to": "release", "revision_comments": ["keep"]})
    back.assert_called_once()
    lock.assert_called_once()
    assert out["stage"] == "release" and out["acceptance_return_to"] is None
    assert out["acceptance_result"] == {"passed": 22}
    assert "suite as last locked was kept" in out["acceptance_open_problems"][0]
    assert "x is skipped" in out["acceptance_open_problems"][0]


def test_a_replanned_sprint_goes_to_the_lead():
    out, _, _ = _kept({"acceptance_return_to": acceptance_nodes.SPRINT_REPLAN})
    assert out["stage"] == "technical_lead"


def test_a_first_writing_is_not_kept():
    assert _kept({"acceptance_return_to": None})[0] is None
    assert _kept({"acceptance_return_to": "release"}, repairing=False)[0] is None


def test_both_ways_a_suite_gives_up_try_it_before_failing_the_run():
    source = inspect.getsource(acceptance_nodes)
    for failing in ("Acceptance suite failed to run after", "Acceptance suite still proves nothing after"):
        at = source.index(failing)
        assert "_kept_as_locked_before(" in source[at - 260:at]
