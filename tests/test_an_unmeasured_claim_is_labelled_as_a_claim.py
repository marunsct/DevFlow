"""What a reviewer or a fixer claimed reaches the next fixer as a claim, not as what was measured (LF.1462, LF.1463).

Measured on one medium run: a reviewer's reading - "FastAPI processes middleware in reverse order of registration ...
exceptions from route handlers won't be caught" - stood word for word under "Actual behavior" of what the brief
called a test failure; nothing had measured it, and its first fixer spent 21 minutes on it, then a second fixer was
sent. "Earlier attempts at this defect, as the harness measured them" printed a fixer's own account of a cause after
"changed no file", where it read as a finding.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

FINDING = json.loads((Path(__file__).parent / "fixtures" / "evidence_records" / "reviewer_finding.json")
                     .read_text(encoding="utf-8"))


def test_a_reviewer_s_reading_is_not_filed_as_the_actual_behaviour() -> None:
    from app.graph.engineering import review_defect

    finding = SimpleNamespace(**FINDING["finding"])

    defect = review_defect(finding, FINDING["why"], "backend")

    assert "reverse order of registration" not in defect.actual_behavior
    assert defect.actual_behavior.startswith(FINDING["why"])
    assert "not measured" in defect.actual_behavior
    assert "reverse order of registration" in defect.description


def test_a_fixer_s_own_account_in_earlier_attempts_is_labelled_its_own(monkeypatch) -> None:
    """The real attempt: no file changed, and the fixer's account of a migration fault it never made."""
    from app.agents import ledger

    monkeypatch.setattr(ledger, "enabled", lambda: True)
    attempt = {"stage": "defect_fix_1_2", "files": [], "outcome": "left open: its tests still fail",
               "did": "The _do_run function in database.py and alembic/env.py was only calling "
                      "context_impl.start_transaction() instead of actually running the Alembic migrations. Changed "
                      "both to call alembic.command.upgrade(alembic_context.get_context()) which p"}
    defect = SimpleNamespace(attempts=[attempt], description="[AC-1] Sign up")

    block = ledger.earlier_attempts(defect)

    line = next(line for line in block.splitlines() if line.startswith("- defect_fix_1_2"))
    assert "changed no file; it said, not measured: \"The _do_run function" in line
    assert line.endswith("-> left open: its tests still fail")
