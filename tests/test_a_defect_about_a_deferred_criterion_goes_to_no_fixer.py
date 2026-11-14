"""A round's defect naming only criteria the suite has deferred goes to no fixer.

Measured on one run: a criterion was deferred with its suite repairs spent, but the round's checks named only one of
its four tests as unable to pass, so the defect about all four went on to fixers; one fix broke 37 tests and was
reverted, and the next round raised it again.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.graph import workflow


def _defect(text):
    return SimpleNamespace(description=text, reproduction_steps="", expected_behavior="", actual_behavior="",
                           affected_files=[], owner="backend")


def test_only_deferred_criteria_are_set_aside(monkeypatch):
    from app.acceptance import suite

    monkeypatch.setattr(suite, "deferred", lambda root: {"AC-19": "its locked tests cannot pass"})
    deferred_only = _defect("[AC-19] One record is never seen by another - the suite says this does not work yet.")
    mixed = _defect("[AC-19] and [AC-2] fail together")
    other = _defect("[AC-2] Sign in gives a token - the suite says this does not work yet.")

    kept, set_aside = workflow._defects_only_about_deferred([deferred_only, mixed, other], "/w")

    assert set_aside == [deferred_only] and kept == [mixed, other]


def test_nothing_deferred_leaves_the_round_as_it_was(monkeypatch):
    from app.acceptance import suite

    monkeypatch.setattr(suite, "deferred", lambda root: {})
    reported = [_defect("[AC-19] fails")]
    assert workflow._defects_only_about_deferred(reported, "/w") == (reported, [])


def test_the_round_sets_them_aside_before_the_backstop():
    source = inspect.getsource(workflow)
    assert source.index("_defects_only_about_deferred(reported, state[") < source.index(
        "unreported_criteria = acceptance_nodes.failing_due_defects(state, reported)")
