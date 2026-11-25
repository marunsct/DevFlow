"""A batch's product change is not put back silently for one regressed test (LF.1447).

Measured on a fast run (deep review 2026-11-25, decisions finding 8; the run's acceptance history): a fix batch took
the suite from 12 to 19 passing tests, and because one test that had passed did not, its product change (`src/app.js`,
the styles) was put back and its tests kept - twice, 20:02 and 20:37 JST - before a third identical rewrite was kept at
20:56 (54 minutes). No `reverted` event was recorded, and the fixers were settled "its own tests still fail" on the
product the harness had restored, so nothing told the next fixer why.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import ci
from app.agents import ledger
from app.graph import engineering
from app.graph.workflow import _with_the_attempt
from app.sprint import Defect, RemediationCycle

REGRESSED = "acceptance: ui.spec.js › [AC-2] Bookmarks are listed newest first via the page"
CHANGED = ["bookmarks/src/app.js", "bookmarks/public/styles.css", "bookmarks/tests/app.test.js"]


def _passing(count: int, *, lost: bool) -> ci.Snapshot:
    acceptance = {f"[AC-{n}] passes": ("passed" if n < count else "failed") for n in range(1, 32)}
    acceptance["ui.spec.js › [AC-2] Bookmarks are listed newest first via the page"] = "failed" if lost else "passed"
    return ci.Snapshot(label="m", unit_ran=True, acceptance_ran=True, unit={"t": "passed"}, acceptance=acceptance)


def _measured(monkeypatch, before, after):
    put_back: list[list[str]] = []
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(engineering, "what_the_fix_did_to_the_install", lambda root, base: "")
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after if not put_back else before)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")
    monkeypatch.setattr(ci, "save", lambda root, snapshot, **kw: None)
    monkeypatch.setattr(ci, "changed_since", lambda root, base: list(CHANGED))
    monkeypatch.setattr(ci, "restore_paths", lambda root, base, paths: put_back.append(list(paths)) or True)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: True)
    return put_back


def test_a_batch_that_gains_more_than_it_loses_is_not_put_back(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "on")
    put_back = _measured(monkeypatch, _passing(12, lost=False), _passing(20, lost=True))

    broke = engineering.after_a_fix(str(tmp_path), "base", "defect_fix_1_batch", "the page script")

    assert broke == []
    assert put_back == []


@pytest.fixture
def _ledger_on(monkeypatch):
    monkeypatch.setenv("DECISION_LEDGER", "on")


def test_a_split_is_recorded_as_a_revert_naming_the_tests_it_broke(tmp_path, monkeypatch, _ledger_on):
    monkeypatch.setenv("KEEP_NET_GAINS", "off")
    _measured(monkeypatch, _passing(12, lost=False), _passing(13, lost=True))
    engineering.after_a_batch(str(tmp_path), "base", "defect_fix_1_batch", "the page script",
                              [("defect_fix_1_8", ["bookmarks/src/app.js"]), ("defect_fix_1_3", ["bookmarks/README.md"])])
    defect = Defect(description="[AC-3] Delete a bookmark via the page - the acceptance suite says this does not "
                                "work yet.", severity="major", reproduction_steps="run the suite",
                    expected_behavior="the item is gone", actual_behavior="it is still listed", owner="ui_ux")
    cycle = RemediationCycle(sprint_goal="bookmarks", defects=[defect])
    result = SimpleNamespace(changed_files=["bookmarks/src/app.js"], decisions=["Rewrote the list rendering"])

    recorded = _with_the_attempt(cycle, 0, "defect_fix_1_8", result, "left open: its tests still fail",
                                 root=str(tmp_path))

    outcome = recorded.defects[0].attempts[-1]["outcome"]
    assert outcome.startswith("reverted")
    assert "[AC-2] Bookmarks are listed newest first via the page" in outcome
    assert "[AC-2] Bookmarks are listed newest first" in ledger.earlier_attempts(recorded.defects[0])


def test_a_fixer_whose_files_were_not_put_back_is_not_charged(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEP_NET_GAINS", "off")
    _measured(monkeypatch, _passing(12, lost=False), _passing(13, lost=True))
    engineering.after_a_batch(str(tmp_path), "base", "defect_fix_1_batch", "the page script",
                              [("defect_fix_1_8", ["bookmarks/src/app.js"]), ("defect_fix_1_3", ["bookmarks/README.md"])])

    assert engineering.what_was_put_back(str(tmp_path), "defect_fix_1_3") == ""
