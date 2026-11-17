"""Dispute rulings that blame one helper the suite defines are one cause, not one per test.

Measured on two runs: a helper (`_compute_words` lost its `+`) and a fixture (`auth_token`, copied with the same
username) each failed many tests; counted per test, the cap deferred right criteria.
"""
from __future__ import annotations

from app.graph.acceptance_nodes import by_shared_cause

SUITE = '''import pytest


@pytest.fixture(scope="session")
def auth_token(base_url):
    return "x"


def _compute_words(text):
    return 1


def test_ac6_delete(auth_token):
    pass
'''


def test_rulings_blaming_one_fixture_are_grouped_and_others_stand_alone():
    rulings = [
        "`test_ac6_delete` cannot pass: the test's own auth_token fixture collides with another session fixture",
        "`test_ac7_restart` cannot pass: the auth_token fixture signs up the same username",
        "`test_ac9_words` cannot pass: the helper `_compute_words` counts letters",
        "`test_ac11_exact` cannot pass: expects 24 for a 25-character input",
    ]
    groups = by_shared_cause(rulings, SUITE)
    assert sorted(len(g) for g in groups) == [1, 1, 2]
    assert any(rulings[0] in g and rulings[1] in g for g in groups)


def test_a_name_the_suite_does_not_define_is_no_shared_cause():
    rulings = ["`test_a` cannot pass: product_store is wrong", "`test_b` cannot pass: product_store is wrong"]
    assert by_shared_cause(rulings, SUITE) == [[rulings[0]], [rulings[1]]]


def test_the_cap_counts_causes_so_a_shared_fixture_takes_one_place(tmp_path):
    from types import SimpleNamespace

    from app.graph.acceptance_nodes import reclassification_room, within_the_cap_by_cause

    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "suite_reclassified_tests": []}
    groups = [["a1", "a2", "a3", "a4"], ["b"], ["c"]]
    kept, past, causes = within_the_cap_by_cause(state, groups)
    # The floor is two causes: the shared fixture's four rulings and one more; the third cause waits.
    assert kept == ["a1", "a2", "a3", "a4", "b"] and past == ["c"] and causes == 2
    assert reclassification_room({**state, "suite_reclassified_causes": 2,
                                  "suite_reclassified_tests": ["a1", "a2", "a3", "a4", "b"]}) == 0
    assert reclassification_room({**state, "suite_reclassified_causes": 1,
                                  "suite_reclassified_tests": ["a1", "a2", "a3", "a4"]}) == 1


def test_the_dispute_groups_rulings_before_the_cap(tmp_path):
    """Two rulings blaming one fixture and a criterion missing from the suite: two causes, not three."""
    from workflow_nodes import a_dispute

    failing = [
        ("test_ac6_delete", "AC-6 a record can be deleted", "409 Conflict"),
        ("test_ac7_restart", "AC-7 records survive a restart", "409 Conflict"),
        ("AC-8 missing from locked suite", "AC-8 records can be renamed", ""),
    ]
    rulings = [
        "`test_ac6_delete` cannot pass: the test's own auth_token fixture collides with another session fixture",
        "`test_ac7_restart` cannot pass: the auth_token fixture signs up the same username",
    ]

    _, asked = a_dispute(tmp_path, failing, rulings, suite_text=SUITE, reopened={"stage": "acceptance_author"})

    (reopen,) = asked["reopen"]
    assert reopen["broken"][:2] == rulings and "missing from the locked suite" in reopen["broken"][2]
    assert reopen["causes"] == 2
