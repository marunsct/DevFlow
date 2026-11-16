"""One refusal behind nearly every failing acceptance test is raised as one defect, not one per criterion (LR.53).

Measured on one run: 16 tests of 14 criteria all failed with `assert 401 == 201` - the product refused the token its own
sign-in issued - and each criterion got a fixer of its own, shown one test, who sent the file back unchanged; the
round ran ten fixers in three hours.
"""
from __future__ import annotations

import re

from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _failing(messages):
    return [{"id": f"AC-{n}", "tests": [{"name": f"t{n}", "outcome": "failed", "message": m}]}
            for n, m in enumerate(messages, 1)]


def test_the_same_refusal_everywhere_is_one_cause():
    failing = _failing(["assert 401 == 201\n where", "assert 401 == 200", "assert 401 in (400, 422)", "assert 401 == 204"])
    assert nodes.one_refusal_for_all(failing) == ("401", 4)
    # A body read after the refused call fails with no status of its own: the same cause (measured beside 401s).
    with_symptoms = _failing(["assert 401 == 201", "assert 401 == 200", "assert 401 == 201", "E   KeyError: 'id'",
                              "E   KeyError: 'id'"])
    assert nodes.one_refusal_for_all(with_symptoms) == ("401", 5)


def test_mixed_failures_or_too_few_criteria_keep_their_own_defects():
    assert nodes.one_refusal_for_all(_failing(["assert 401 == 201", "assert 404 == 200", "assert 500 == 200",
                                               "AssertionError: title"])) is None
    assert nodes.one_refusal_for_all(_failing(["assert 401 == 201", "assert 401 == 200"])) is None
    assert nodes.one_refusal_for_all(_failing(["assert 404 == 200"] * 4)) is None


def test_the_round_raises_it_alone_and_its_words_ban_the_product_s_nouns():
    import inspect

    source = inspect.getsource(nodes.failing_due_defects)
    at = source.index("refused = one_refusal_for_all(failing)")
    assert "return [*installs, *defects]" in source[at:at + 2200]
    words = source[at:at + 2200]
    assert not BANNED.search(re.sub(r"#.*", "", words))
