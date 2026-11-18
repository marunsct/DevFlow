"""What was tried on a cause outlives the fix cycle it was tried in: fixers and the re-planning lead read it.

Deep review 2026-11-18, item 1.4: when a sprint ran out of fix rounds it was planned again with its remediation cycle
cleared, and each defect's record of what had been tried went with it. The next cycle's fixers and the lead were shown
the open defects but not what had failed on them. Measured: one run was planned again three times with the same change
each time, a re-plan costing about 34 active minutes, and the share of defects fixed fell from 29% at a first attempt
to 22% and then 11%.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

import the_fix_stage

from app.agents.specialists import SpecialistOutput
from app.graph import cause_journal

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _a_cause(description="The count is wrong", tests=("counts each record",)):
    return the_fix_stage.a_defect(description, kind="failing_test", evidence=[{"test": t} for t in tests],
                                  cause_key="failing_test:" + "|".join(f"test:{t}" for t in tests))


def test_a_fix_tried_in_one_cycle_is_shown_to_the_fixer_of_the_same_cause_after_a_replan(tmp_path):
    reverted = SpecialistOutput(changed_files=["app/count.js"], decisions=["Counted from the cached list"])
    the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, _a_cause()), answer=reverted,
                      broke=["acceptance: lists records"])

    # The sprint is planned again: a new cycle, the same cause raised in other words.
    again = the_fix_stage.a_state(tmp_path, _a_cause("Counting answers a stale number"), test_round=0)
    _, seen = the_fix_stage.run(tmp_path, again)

    [sent] = seen.requests
    assert cause_journal.HEADING in sent
    tried = sent[sent.index(cause_journal.HEADING):]
    assert "`app/count.js`" in tried and "Counted from the cached list" in tried and "reverted" in tried


def test_a_different_cause_is_not_shown_another_cause_s_attempts(tmp_path):
    reverted = SpecialistOutput(changed_files=["app/count.js"], decisions=["Counted from the cached list"])
    the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, _a_cause()), answer=reverted, broke=["x"])

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(
        tmp_path, _a_cause("Sorting is wrong", tests=("sorts by date",)), test_round=0))

    assert cause_journal.HEADING not in seen.requests[0]


def test_the_lead_planning_the_sprint_again_reads_what_failed_on_each_cause(tmp_path):
    defect = _a_cause()
    cause_journal.record(tmp_path, defect, {"stage": "defect_fix_1_0", "files": ["app/count.js"],
                                            "did": "Counted from the cached list", "outcome": "reverted: it broke x"},
                         sprint=0)
    cause_journal.record(tmp_path, defect, {"stage": "defect_fix_2_0", "files": ["app/store.js"],
                                            "did": "Cleared the cache on write", "outcome": "left open: its tests still fail"},
                         sprint=0)

    text = cause_journal.for_a_replan(tmp_path, 0)

    assert "The count is wrong" in text and "2 time(s)" in text
    assert text.index("Cleared the cache on write") < text.index("Counted from the cached list"), "newest first"
    assert cause_journal.for_a_replan(tmp_path, 1) == "", "another sprint's causes are not this plan's"


def test_what_the_journal_tells_a_model_holds_no_product_words(tmp_path):
    defect = _a_cause()
    cause_journal.record(tmp_path, defect, {"stage": "s", "files": ["a"], "did": "d", "outcome": "reverted"}, sprint=0)
    cause_journal.add_hypothesis(tmp_path, defect, "h")
    from app.graph import localisation

    for text in (cause_journal.tried_before(tmp_path, defect), cause_journal.for_a_replan(tmp_path, 0),
                 localisation.DIAGNOSIS_ROLE):
        assert text and not BANNED.search(text)


class _Spy:
    """The diagnosis model, at the edge: records what it is asked and answers one object."""

    def __init__(self):
        self.asked = []

    def invoke(self, messages, **kwargs):
        self.asked.append((messages, kwargs))
        return SimpleNamespace(content='{"files": ["app/count.js"], "symbols": ["count"], '
                                       '"hypothesis": "The count is read before the write is saved."}')


def _failed_twice(root, defect):
    for n in (1, 2):
        cause_journal.record(root, defect, {"stage": f"defect_fix_{n}_0", "files": ["app/count.js"],
                                            "did": "Counted again", "outcome": "left open: its tests still fail"})


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("DIAGNOSE_A_RECURRING_CAUSE", "on")


def test_a_cause_that_failed_twice_is_diagnosed_once_and_the_fixer_is_given_the_diagnosis(tmp_path, on):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "count.js").write_text("export function count() {}\n")
    defect, spy = _a_cause(), _Spy()
    _failed_twice(tmp_path, defect)

    said = cause_journal.diagnosed(tmp_path, defect, "expected 3, got 2", spy)
    cause_journal.diagnosed(tmp_path, defect, "expected 3, got 2", spy)

    assert len(spy.asked) == 1, "one diagnosis, not one per fix"
    messages, kwargs = spy.asked[0]
    assert "tools" not in kwargs
    assert "Counted again" in messages[-1].content, "it is told what was tried"
    assert "read before the write is saved" in said
    shown = cause_journal.tried_before(tmp_path, defect)
    assert cause_journal.DIAGNOSIS in shown and "read before the write is saved" in shown


def test_a_cause_that_failed_once_is_not_diagnosed(tmp_path, on):
    defect, spy = _a_cause(), _Spy()
    cause_journal.record(tmp_path, defect, {"stage": "s", "files": [], "did": "", "outcome": "reverted"})

    assert cause_journal.diagnosed(tmp_path, defect, "f", spy) == ""
    assert spy.asked == []


def test_nothing_is_diagnosed_with_the_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("DIAGNOSE_A_RECURRING_CAUSE", "off")
    defect, spy = _a_cause(), _Spy()
    _failed_twice(tmp_path, defect)

    assert cause_journal.diagnosed(tmp_path, defect, "f", spy) == ""
    assert spy.asked == []
