"""A defect that the product does not start is never closed by passing unit tests (measured live).

The dispatch re-measure falls back to the unit tests for a defect that names no
criterion. For "the product does not start for the acceptance suite" they pass
whether or not the suite can start the product, so the defect was closed without
a fixer every round - six times in one run - and raised again at the next
measurement, while no fixer ever saw it.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.graph import acceptance_nodes, workflow
from app.sprint import Defect, RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _defect(description: str) -> Defect:
    return Defect(
        description=description, severity="blocking", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="backend",
    )


def test_the_unit_tests_cannot_answer_for_a_product_that_does_not_start(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (True, ""))

    answer = workflow._the_defect_s_tests_pass(
        Path(tmp_path), _defect(acceptance_nodes.THE_PRODUCT_DOES_NOT_START)
    )

    assert answer is None


def test_such_a_defect_is_dispatched_to_a_fixer_though_the_unit_tests_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (True, ""))
    cycle = RemediationCycle(
        sprint_goal="Sprint 1", defects=[_defect(acceptance_nodes.THE_PRODUCT_DOES_NOT_START)]
    )
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 1}

    assert workflow._closed_if_an_earlier_fix_resolved_it(state, cycle, 0) is None


def test_a_defect_about_unit_tests_is_still_answered_by_them(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (True, ""))

    assert workflow._the_defect_s_tests_pass(Path(tmp_path), _defect("The unit tests fail.")) is True


def test_the_wording_uses_none_of_the_banned_words():
    assert not BANNED.search(acceptance_nodes.THE_PRODUCT_DOES_NOT_START)
