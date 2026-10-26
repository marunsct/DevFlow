"""A criterion due now that no locked test names goes back to QA from the test round, not to a product fixer.

Measured on a small-model run: the suite was locked with one criterion untested; every round raised it as a product
defect, the dispatch closed it at once because none of its tests failed, and the sprint was planned again - four
rounds and a re-plan in two minutes at 17 of 18 with every test passing.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
GAP_15 = 'AC-15 ("start.sh starts the service") has no test whose name carries `AC-15`. Write a test for it.'
GAP_20 = 'AC-20 ("later") has no test whose name carries `AC-20`. Write a test for it.'


def test_a_due_criterion_with_no_test_is_among_what_the_round_reopens(monkeypatch):
    monkeypatch.setattr(nodes, "run_for_sprint", lambda state: (SimpleNamespace(), ["AC-1", "AC-15"]))
    monkeypatch.setattr(nodes, "_root", lambda state: "/nowhere")
    for name in ("tests_that_cannot_pass", "tests_left_behind_by_their_own_change", "vacuous_green"):
        monkeypatch.setattr(suite, name, lambda *a, **k: [])
    monkeypatch.setattr(suite, "gaps", lambda root: [GAP_15, GAP_20])
    monkeypatch.setattr(nodes.acceptance_requests, "acceptance_block", lambda result, due: "block")

    _, broken = nodes.acceptance_for_round({})

    assert broken == [GAP_15]
    assert not BANNED.search(" ".join(broken))
