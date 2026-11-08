"""A second attempt does not repeat a whole-file rewrite that sent every file back unchanged (harness review HR2.fix.4).

Rewrite after rewrite fixed 16% of defects, a rewrite then the agent loop 33%; the repeated-prompt stop acted only
after three byte-identical prompts, which a refreshed failure text defeats.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import rewritten_fixes
from app.observability.defect_ledger import defect_id

DEFECT = SimpleNamespace(description="[AC-2] lists every note", source="acceptance", owner="backend")


def _records(*events):
    me = defect_id(DEFECT)
    return [{"defect_id": me, "event": event, "detail": detail} for event, detail in events]


def test_an_all_unchanged_rewrite_is_not_repeated() -> None:
    records = _records(("shown", "fingerprint a"), ("rewrite reply", "unchanged: notes/app.py"))
    assert rewritten_fixes._the_last_rewrite_changed_nothing(DEFECT, ["notes/app.py"], records)


def test_a_rewrite_that_changed_a_file_or_was_shown_other_files_is_tried() -> None:
    changed = _records(("shown", "a"), ("rewrite reply", "unchanged: notes/app.py"), ("rewrite reply", "changed: notes/store.py"))
    assert not rewritten_fixes._the_last_rewrite_changed_nothing(DEFECT, ["notes/app.py", "notes/store.py"], changed)
    other = _records(("shown", "a"), ("rewrite reply", "unchanged: notes/app.py"))
    assert not rewritten_fixes._the_last_rewrite_changed_nothing(DEFECT, ["notes/store.py"], other)


def test_after_the_agent_loop_ran_a_rewrite_is_tried_again() -> None:
    records = _records(("shown", "a"), ("rewrite reply", "unchanged: notes/app.py"), ("shown", "the loop"))
    assert not rewritten_fixes._the_last_rewrite_changed_nothing(DEFECT, ["notes/app.py"], records)


def test_the_rewrite_hands_the_attempt_to_the_loop(tmp_path, monkeypatch) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(rewritten_fixes, "_the_last_rewrite_changed_nothing", lambda defect, files, records=None: True)
    asked = []
    model = SimpleNamespace(invoke=lambda messages, **k: asked.append(messages))
    assert rewritten_fixes.fix_by_rewriting(DEFECT, tmp_path, model, files=["notes/app.py"]) is None
    assert asked == [], "no rewrite request is sent"
