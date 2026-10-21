"""Lessons are proposed from what the harness recorded, for the owner to approve (plans RL.1-RL.3).

Behind `LESSON_DISTILLER`, off until measured. Nothing a model writes becomes a
lesson; nothing becomes one without the owner's approval.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest import mock

from app.observability.run_kpis import kpis
from app.plugins import lesson_distiller, lessons
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RECORDS = [
    {"kind": "defect", "event": "reverted", "round": 1, "index": 0, "detail": "broke 2 test(s) that passed before it: a; b"},
    {"kind": "defect", "event": "raised", "round": 0, "index": 1,
     "description": "The code imports packages no manifest declares: `bcrypt` (imported in `app/auth.py`)."},
    *[{"kind": "defect", "event": "left open", "round": r, "index": 3} for r in (1, 2, 3)],
]


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / ".harness").mkdir()
    (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "python-flask-api", "project": "app"}))
    transcript = tmp_path / "run.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in RECORDS))
    return transcript


def test_each_recorded_signal_proposes_one_lesson_in_no_banned_word():
    found = lesson_distiller.proposals(RECORDS)

    assert [p["trigger"] for p in found] == [
        "a fix reverted for breaking tests that passed before it",
        "code imports a package no manifest declares",
        "a defect that needed more than 2 fix attempts",
    ]
    assert "`bcrypt`" in found[1]["rule"]
    assert not any(BANNED.search(p["rule"] + p["trigger"]) for p in found)


def test_on_they_are_proposed_for_the_stack_and_an_approved_one_recurring_is_counted(tmp_path):
    transcript, store = _workspace(tmp_path), tmp_path / "lessons.json"

    with mock.patch.dict(os.environ, {"LESSON_DISTILLER": "on"}):
        first = lesson_distiller.distil(transcript, tmp_path, path=store)
        lessons.decide(first[0]["id"], True, path=store)
        again = lesson_distiller.distil(transcript, tmp_path, path=store)

    assert {l["status"] for l in first} == {"proposed"} and all(l["stack"] == "python-flask-api" for l in first)
    assert again[0]["recurred_runs"] == 1 and len(lessons.load(store)) == 3


def test_off_nothing_is_proposed(tmp_path):
    transcript, store = _workspace(tmp_path), tmp_path / "lessons.json"

    with mock.patch.dict(os.environ, {"LESSON_DISTILLER": ""}):
        assert lesson_distiller.distil(transcript, tmp_path, path=store) == []
    assert lessons.load(store) == []


def test_the_kpis_count_the_calls_shown_lessons():
    shown = {"kind": "model_request", "at": "2026-10-21T00:00:00+00:00", "messages": [{"content": lessons.FRAME + " x"}]}
    plain = {"kind": "model_request", "at": "2026-10-21T00:00:01+00:00", "messages": [{"content": "y"}]}

    assert kpis([shown, plain])["lessons_shown_calls"] == 1


def test_the_loop_lists_them_and_distils_after_each_run():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    assert 'lessons) shift; in_worker lessons.py' in script and '"$0" lessons distil "$run"' in script
