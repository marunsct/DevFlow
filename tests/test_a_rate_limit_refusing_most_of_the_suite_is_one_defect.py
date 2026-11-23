"""A rate limit that refuses most of the suite is one defect naming the limit, even beside other failures (found on a run).

Measured on one run: a sign-up limit of ten an hour answered 429 to 66 of 92 failing tests (the suite signs up an
account per test from one address); 26 others failed otherwise, so the rule for one refusal behind every failure gave
up, each criterion got its own fixer for eight hours, and the suite never moved past 17 of 97.
"""
from __future__ import annotations

import re

from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
A_429 = "Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 201\n    Received: 429\n"
A_404 = "Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 200\n    Received: 404\n"


def _failing(messages):
    return [{"id": f"AC-{n}", "tests": [{"name": f"t{n}", "outcome": "failed", "message": m}]}
            for n, m in enumerate(messages, 1)]


def test_most_tests_answered_429_is_one_cause_though_others_failed_otherwise():
    failing = _failing([A_429] * 7 + [A_404] * 3)
    assert nodes.one_refusal_for_all(failing) == ("429", 7)


def test_a_429_in_a_few_tests_keeps_each_criterion_s_own_defect():
    assert nodes.one_refusal_for_all(_failing([A_429] * 2 + [A_404] * 6)) is None


def test_another_code_beside_other_answers_still_keeps_its_own_defects():
    assert nodes.one_refusal_for_all(_failing(["assert 401 == 201"] * 7 + [A_404] * 3)) is None


def test_the_fixer_is_told_it_is_a_limit_to_size_not_to_remove():
    said = nodes.A_LIMIT_THE_SUITE_MEETS
    assert "Keep the limit" in said and "read it from the environment" in said
    assert not BANNED.search(said)
