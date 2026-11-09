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
