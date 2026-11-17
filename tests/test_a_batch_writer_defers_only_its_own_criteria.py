"""A batch of the suite's writer decides about its own batch's criteria, never another batch's (found on a run).

Measured on one run (BATCH_ACCEPTANCE_AUTHOR on): the first batch's writer listed "Part 2 and Part 3 of the acceptance
suite will cover AC-7 ... AC-18" in its blockers; the harness read blockers as criteria no automated test can check,
deferred twelve of eighteen, the suite was locked with six tests, the product was built to them, and the escalation
stopped the run as more than half the product undelivered.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import acceptance_nodes


def _group(*ids):
    return [SimpleNamespace(id=i) for i in ids]


def test_blockers_naming_other_batches_criteria_are_not_its_to_set_aside():
    blockers = [
        "Part 2 and Part 3 of the acceptance suite will cover AC-7 (note schema), AC-8 (POST status 201), AC-12.",
        "AC-3: the notes are listed by a person reading the page; no automated test can judge it.",
        "No product to run yet; every test fails until it is built.",
    ]
    kept = acceptance_nodes.blockers_of_its_batch(blockers, _group("AC-1", "AC-2", "AC-3"))
    assert kept == [blockers[1], blockers[2]]


def test_a_blocker_naming_its_own_and_another_batch_s_criterion_keeps_only_its_own():
    kept = acceptance_nodes.blockers_of_its_batch(["AC-2, AC-9: a third party must approve them."], _group("AC-1", "AC-2"))
    assert kept == ["AC-2: a third party must approve them."]
