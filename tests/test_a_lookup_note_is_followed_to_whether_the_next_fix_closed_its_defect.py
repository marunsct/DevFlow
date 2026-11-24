"""Each lookup note a fixer is shown has an id tied to its defect, and the ledger says whether the next fix closed that
defect; `loop.sh effects` prints the share against stuck fixes made without a note (plan HK.4, LF.1296).

Measured before it: the ledger said only that a search was made ("T1 stuck: searched ...: 3 found"). Whether the note
helped was counted by hand across runs (2 of 9 looked-up defects fixed afterwards), and a note found once and shown
again to another defect left no record at all.
"""
from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph import stuck_lookup
from app.observability import defect_ledger, transcript
from app.tools import lookups

EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
STACK = SimpleNamespace(language="Python", framework="FastAPI")


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-notes")

    def look_up(error, stack_words="", private_words=(), **_k):  # the network's edge
        return {"query": "OverflowError: Python int too large to convert to SQLite INTEGER", "asked": [
            "stack exchange", "github issues"], "found": [{
                "source": "Stack Overflow, accepted answer", "title": "int too large", "date": "2024-01-01",
                "url": "https://stackoverflow.com/q/1", "excerpt": "Check the id against 2**63 - 1 first."}]}

    monkeypatch.setattr(lookups, "look_up", look_up)
    yield lambda: [r for r in transcript.read_transcript("run-notes") if r.get("kind") == "defect"]


def _stuck(description: str) -> SimpleNamespace:
    return SimpleNamespace(description=description, source="edge probe", owner="backend",
                           actual_behavior="the server printed: OverflowError: Python int too large to convert to "
                                           "SQLite INTEGER", attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])


def test_a_note_shown_carries_its_id_and_the_defect_s_next_outcome_says_whether_it_closed_it(tmp_path, run):
    first, second = _stuck("DELETE at a huge id answers 500"), _stuck("PATCH at a huge id answers 500")

    stuck_lookup.section(tmp_path, first, STACK, "defect_fix_2_0")
    stuck_lookup.section(tmp_path, second, STACK, "defect_fix_2_1")
    defect_ledger.note("fixed", "defect_fix_2_0", defect=first, detail="kept")
    defect_ledger.note("left open", "defect_fix_2_1", defect=second, detail="its own tests still fail")

    ledger = run()
    shown = [r for r in ledger if r["event"] in {"lookup", "lookup shown again"}]
    assert [r["event"] for r in shown] == ["lookup", "lookup shown again"]
    assert shown[0]["note"] == shown[1]["note"] and shown[0]["note"] in shown[0]["detail"]
    assert [r["defect_id"] for r in shown] == [defect_ledger.defect_id(first), defect_ledger.defect_id(second)]
    assert shown[0]["answered"] == {"stack exchange": 1, "github issues": 0}
    outcomes = {r["defect_id"]: r for r in ledger if r["event"] == "lookup outcome"}
    assert outcomes[defect_ledger.defect_id(first)]["closed"] is True
    assert outcomes[defect_ledger.defect_id(second)]["closed"] is False
    assert "not closed by the next fix (left open)" in outcomes[defect_ledger.defect_id(second)]["detail"]


def test_an_outcome_with_no_note_shown_since_the_last_one_records_nothing_more(tmp_path, run):
    defect = _stuck("DELETE at a huge id answers 500")
    stuck_lookup.section(tmp_path, defect, STACK, "defect_fix_2_0")
    defect_ledger.note("left open", "defect_fix_2_0", defect=defect)

    defect_ledger.note("fixed", "defect_fix_3_0", defect=defect)

    assert [r["event"] for r in run()].count("lookup outcome") == 1


def _ledger(event: str, defect: str, **more) -> dict:
    return {"kind": "defect", "event": event, "defect_id": defect, **more}


def test_effects_counts_looked_up_defects_closed_by_the_next_fix_against_stuck_ones_without_a_note():
    effects = runpy.run_path(str(EFFECTS))["effects"]
    records = [
        # Looked up after a failed fix, then fixed.
        _ledger("reverted", "a"), _ledger("lookup", "a", found=2, answered={"stack exchange": 2, "github issues": 0}),
        _ledger("fixed", "a"),
        # Looked up (a record written before the `found` field), then left open again.
        _ledger("left open", "b"), _ledger("lookup", "b", detail="T1 stuck: searched 'x': 3 found from stack exchange"),
        _ledger("left open", "b"),
        # A search that found nothing showed no note: not counted as looked up.
        _ledger("left open", "c"), _ledger("lookup", "c", found=0, answered={"stack exchange": 0}),
        _ledger("left open", "c"),
        # Stuck with no note: closed once by the next fix, not closed once.
        _ledger("left open", "d"), _ledger("fixed", "d"),
        # A note from the cache, then fixed: it asked no source, so no source's rate counts it.
        _ledger("lookup", "f", found=1, cached=True, answered={"stack exchange": 1}), _ledger("fixed", "f"),
        # A note still waiting for its fix.
        _ledger("lookup shown again", "e"),
        # A registry lookup is a run note, not a defect's.
        {"kind": "defect", "event": "lookup", "defect_id": "", "detail": "T4 registry versions: 1 found"},
    ]

    lines = "\n".join(effects(records, ""))

    assert ("HK.4 looked-up defects closed by the next fix: 2 of 3 (1 with no outcome yet); stuck fixes without a "
            "note: 1 of 2 closed by their next fix") in lines
    assert "KS.6 lookup sources answering: stack exchange 1 of 2, github issues 0 of 1" in lines


def test_effects_says_when_no_note_was_shown():
    effects = runpy.run_path(str(EFFECTS))["effects"]

    lines = "\n".join(effects([_ledger("left open", "a")], ""))

    assert "HK.4 looked-up defects closed by the next fix: not reached" in lines
    assert "KS.6 lookup sources answering: not reached" in lines
