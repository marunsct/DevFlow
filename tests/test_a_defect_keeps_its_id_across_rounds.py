"""A defect raised again in the next round keeps its id (harness review F8).

The ledger keyed defects by round and index, so the same defect raised again was a new row and no outcome KPI could
follow one defect to its end.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.observability.defect_ledger import defect_id


def _defect(description, source="acceptance suite", owner="backend"):
    return SimpleNamespace(description=description, source=source, owner=owner)


def test_the_same_defect_in_two_rounds_has_one_id():
    first = _defect("[AC-5] Delete a note - `DELETE /notes/3` answered 500 after 2 tries")
    again = _defect("[AC-5] Delete a note - `DELETE /notes/17` answered 500 after 4 tries")
    assert defect_id(first) == defect_id(again)


def test_another_criterion_or_owner_is_another_defect():
    base = _defect("[AC-5] Delete a note - the acceptance suite says this does not work yet.")
    assert defect_id(base) != defect_id(_defect("[AC-6] Delete a note - the acceptance suite says this does not work yet."))
    assert defect_id(base) != defect_id(_defect(base.description, owner="testing"))


def _rewritten(tmp_path, monkeypatch, replies):
    """A one-file rewrite of `app.py` answered with `replies`; the ledger's records, read back from the transcript."""
    from app.graph import rewritten_fixes
    from app.observability import transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-ledger")
    (tmp_path / "data" / "transcripts").mkdir(parents=True)
    (tmp_path / "app.py").write_text("value = 1\n")
    defect = SimpleNamespace(description="[AC-3] Fetch one note", source="acceptance suite", owner="backend",
                             expected_behavior="It answers", actual_behavior="app.py:1 is wrong",
                             affected_files=["app.py"], reproduction_steps=[])
    answers = list(replies)
    model = SimpleNamespace(invoke=lambda messages, **_: SimpleNamespace(content=answers.pop(0)))

    rewritten_fixes.fix_by_rewriting(defect, tmp_path, model, write=lambda base, path, content: None,
                                     diagnose=lambda files: [])
    return [(r["event"], r["detail"]) for r in transcript.read_transcript("run-ledger", {"defect"})]


def test_a_one_file_rewrite_records_what_it_was_shown(tmp_path, monkeypatch):
    """Measured live: two rewrites ran with no `shown` record, and the ledger read as if no fixer had run."""
    ledger = _rewritten(tmp_path, monkeypatch, ["```python\nvalue = 2\n```"])

    assert [event for event, _ in ledger][0] == "shown"
    assert "fingerprint" in ledger[0][1]


@pytest.mark.parametrize(("reply", "kind"), [
    ("```python\nvalue = 2\n```", "changed"),
    ("```python\nvalue = 1\n```", "unchanged"),
    ("```python\n```", "no block"),
])
def test_each_rewrite_reply_is_recorded_by_kind(tmp_path, monkeypatch, reply, kind):
    """HR2.fix.1: 42% of rewrite replies sent the file back unchanged, and nothing recorded it."""
    ledger = _rewritten(tmp_path, monkeypatch, [reply, reply, reply])

    assert ("rewrite reply", f"{kind}: app.py") in ledger
