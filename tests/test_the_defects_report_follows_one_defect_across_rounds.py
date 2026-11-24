"""`loop.sh defects` follows one defect across rounds by its stable id (HR2.fix.7).

Measured: 171 of 808 defects since 11-01 were raised in two or more rounds and the report listed each round's copy
apart, so the attempt curve (29% -> 22% -> 11% fixed) and how such defects end could not be read from it.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "defects.py"


def _function():
    text = SCRIPT.read_text(encoding="utf-8")
    head = text[:text.index("run = sys.argv[1]")]
    namespace: dict = {}
    exec(compile(head, str(SCRIPT), "exec"), namespace)
    return namespace["stories_by_id"]


def test_a_defect_raised_twice_is_one_story_with_its_outcomes_in_order():
    stories_by_id = _function()
    events = [
        {"kind": "defect", "event": "raised", "defect_id": "ab12", "round": 0, "description": "[AC-5] delete"},
        {"kind": "defect", "event": "left open", "defect_id": "ab12", "round": 0},
        {"kind": "defect", "event": "raised", "defect_id": "ab12", "round": 1, "description": "[AC-5] delete"},
        {"kind": "defect", "event": "fixed", "defect_id": "ab12", "round": 1},
        {"kind": "defect", "event": "raised", "defect_id": "cd34", "round": 0, "description": "[AC-9] list"},
        {"kind": "defect", "event": "fixed", "defect_id": "cd34", "round": 0},
    ]
    stories = stories_by_id(events)
    assert list(stories) == ["ab12"]
    assert stories["ab12"]["rounds"] == [0, 1] and stories["ab12"]["outcomes"] == ["left open", "fixed"]
    assert stories["ab12"]["ending"] == "fixed"


def test_a_note_about_the_run_is_not_shown_as_a_defect(tmp_path):
    """Measured: a registry lookup before drafting, written to the ledger with no defect, was listed as a defect
    'raised before the ledger' in sprint '?'."""
    import json
    import os
    import subprocess
    import sys

    records = [
        {"at": "2026-11-24T05:52:37", "kind": "defect", "event": "lookup", "stage": "drafting", "defect_id": "",
         "index": None, "sprint": None, "detail": "registry versions before drafting: 1 asked, 1 found"},
        {"at": "2026-11-24T06:10:00", "kind": "defect", "event": "raised", "stage": "test_round_0", "defect_id": "ab12",
         "index": 0, "sprint": 0, "round": 0, "source": "acceptance", "description": "[AC-1] sign in"},
    ]
    (tmp_path / "run-x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    shown = subprocess.run([sys.executable, str(SCRIPT), "run-x"], capture_output=True, text=True, check=True,
                           env={**os.environ, "TRANSCRIPTS_DIR": str(tmp_path)}).stdout

    assert "1 defect(s) - 1 acceptance" in shown
    assert "raised before the ledger" not in shown
    assert "notes about the run, not one defect (1)" in shown and "registry versions" in shown


def test_an_event_with_only_the_defect_s_id_is_listed_under_that_defect(tmp_path):
    """Measured: the rewrite path's 'shown' and 'rewrite reply' and each stage's 'attempt calls' carry the id and no
    index, and were listed as a defect 'raised before the ledger' in sprint '?'."""
    import json
    import os
    import subprocess
    import sys

    records = [
        {"at": "2026-11-24T06:00:00", "kind": "defect", "event": "raised", "stage": "test_round_0", "defect_id": "ab12",
         "index": 0, "sprint": 0, "round": 0, "source": "test round", "description": "The unit tests fail."},
        {"at": "2026-11-24T06:01:00", "kind": "defect", "event": "rewrite reply", "stage": "defect_fix",
         "defect_id": "ab12", "index": None, "sprint": None, "detail": "changed: tests/app.test.js"},
        {"at": "2026-11-24T06:02:00", "kind": "defect", "event": "fixed", "stage": "defect_fix_1_0", "defect_id": "ab12",
         "index": 0, "sprint": 0, "detail": "rewrote the tests"},
    ]
    (tmp_path / "run-y.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    shown = subprocess.run([sys.executable, str(SCRIPT), "run-y"], capture_output=True, text=True, check=True,
                           env={**os.environ, "TRANSCRIPTS_DIR": str(tmp_path)}).stdout

    assert "sprint ?" not in shown and "raised before the ledger" not in shown
    assert shown.index("rewrite reply") < shown.index("fixed - rewrote the tests")
