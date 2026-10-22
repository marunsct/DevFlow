"""A reverted fix's log line says what it had made pass, as well as what it broke.

Measured live: a fix that rewrote the served page was reverted for breaking one
test, and nothing recorded what it had fixed - the snapshot after a reverted fix
is not kept. Whether a whole fix should go for one broken test cannot be judged
without that number.
"""

from __future__ import annotations

import logging

from app import ci
from app.graph import engineering


def test_the_revert_names_what_the_fix_had_made_pass(monkeypatch, caplog):
    before = ci.Snapshot(label="latest", acceptance={"a": "passed", "b": "failed", "c": "failed"}, acceptance_ran=True)
    after = ci.Snapshot(label="after", acceptance={"a": "failed", "b": "passed", "c": "passed"}, acceptance_ran=True)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: True)

    with caplog.at_level(logging.WARNING, logger=engineering.logger.name):
        broke = engineering.after_a_fix("/workspace", "abc1234", "defect_fix_2_11", "the served page")

    assert broke == ["acceptance: a"]
    assert "broke 1 test(s) that passed before it, and had made 2 pass that did not" in caplog.text
