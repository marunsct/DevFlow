"""A defect raised again in the next round keeps its id (harness review F8).

The ledger keyed defects by round and index, so the same defect raised again was a new row and no outcome KPI could
follow one defect to its end.
"""
from __future__ import annotations

from types import SimpleNamespace

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


def test_a_one_file_rewrite_records_what_it_was_shown(monkeypatch):
    """Measured live: two rewrites ran with no `shown` record, and the ledger read as if no fixer had run."""
    from app.graph import rewritten_fixes
    from app.observability import defect_ledger

    seen = []
    monkeypatch.setattr(defect_ledger, "shown", lambda stage, defect, request, **_: seen.append((stage, request)))
    rewritten_fixes._note_what_the_rewrite_was_shown(_defect("[AC-3] Fetch one note"), "--- Defect ---\nfix it")
    assert seen and seen[0][1].startswith("--- Defect ---")
    import inspect

    assert "_note_what_the_rewrite_was_shown(defect, asked)" in inspect.getsource(rewritten_fixes.fix_by_rewriting)


def test_each_rewrite_reply_is_recorded_by_kind(monkeypatch):
    """HR2.fix.1: 42% of rewrite replies sent the file back unchanged, and nothing recorded it."""
    from app.graph import rewritten_fixes
    from app.observability import defect_ledger

    seen = []
    monkeypatch.setattr(defect_ledger, "note", lambda event, stage, **kw: seen.append((event, kw.get("detail"))))
    rewritten_fixes._note_the_reply(_defect("[AC-3] Fetch one note"), "src/app.py", "unchanged")
    assert seen == [("rewrite reply", "unchanged: src/app.py")]
    import inspect

    source = inspect.getsource(rewritten_fixes.fix_by_rewriting)
    for kind in ('"edit not applied"', '"no block"', '"changed" if content != current else "unchanged"'):
        assert kind in source
