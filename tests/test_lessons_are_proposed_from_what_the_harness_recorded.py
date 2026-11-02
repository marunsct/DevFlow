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
    {"kind": "defect", "event": "reverted", "round": 1, "index": 0, "detail": "broke 2 test(s) that passed before it: unit: a; acceptance: b"},
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
    assert "`bcrypt`" not in found[1]["rule"], "a stack's rule names no one product's packages"
    assert not any(BANNED.search(p["rule"] + p["trigger"]) for p in found)


def test_on_they_are_proposed_for_the_stack_and_an_approved_one_recurring_is_counted(tmp_path):
    transcript, store = _workspace(tmp_path), tmp_path / "lessons.json"

    with mock.patch.dict(os.environ, {"LESSON_DISTILLER": "on"}):
        first = lesson_distiller.distil(transcript, tmp_path, path=store)
        lessons.decide(first[0]["id"], True, path=store)
        again = lesson_distiller.distil(transcript, tmp_path, path=store)
        once_more = lesson_distiller.distil(transcript, tmp_path, path=store)

    assert {l["status"] for l in first} == {"proposed"} and all(l["stack"] == "python-flask-api" for l in first)
    assert again[0]["recurred_runs"] == 1 and len(lessons.load(store)) == 3
    assert once_more[0]["recurred_runs"] == 1, "the same run distilled again is not another recurrence"


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


def test_the_rule_on_a_reverted_fix_says_what_the_harness_does():
    # A fix that gains enough is kept over what it broke (`net_gain`, `unit_tests_disagree`): a rule saying any such
    # change is reverted is false, and it reached prompts on every stack that approved it.
    rule = next(p["rule"] for p in lesson_distiller.proposals(RECORDS) if "reverted" in p["trigger"])

    assert "is reverted" not in rule and "weighs" in rule
    assert not BANNED.search(rule)


def test_a_fix_reverted_for_anything_but_a_named_broken_test_is_no_evidence_of_one():
    for detail in (
        "broke 20 test(s) that passed before it: the product no longer builds or starts after it (no test could reach it)",
        "broke 1 test(s) that passed before it: it wrote code the language service is sure fails when it runs",
    ):
        record = {"kind": "defect", "event": "reverted", "round": 1, "index": 0, "detail": detail}
        assert lesson_distiller.proposals([record]) == []


def test_each_proposal_quotes_what_the_transcript_recorded():
    found = {p["trigger"]: p["evidence"] for p in lesson_distiller.proposals(RECORDS)}

    assert "unit: a" in found["a fix reverted for breaking tests that passed before it"]
    assert "`bcrypt`" in found["code imports a package no manifest declares"]
    assert "3" in found["a defect that needed more than 2 fix attempts"]


def test_a_lesson_counts_the_runs_that_showed_it_and_keeps_what_they_recorded(tmp_path):
    store = tmp_path / "lessons.json"
    for run in ("run-a", "run-b", "run-a"):
        lesson = lessons.propose("s", "t", "A rule.", 1, run_id=run, evidence=f"seen on {run}", path=store)

    assert lesson["evidence_runs"] == 2 and lesson["evidence_in"] == ["run-a", "run-b"]
    assert lesson["evidence"] == ["run-a: seen on run-a", "run-b: seen on run-b"]


def test_distilling_a_run_records_it_as_the_lesson_s_evidence(tmp_path):
    transcript, store = _workspace(tmp_path), tmp_path / "lessons.json"

    with mock.patch.dict(os.environ, {"LESSON_DISTILLER": "on"}):
        done = lesson_distiller.distil(transcript, tmp_path, path=store)

    assert all(l["evidence_in"] == ["run"] and l["evidence"] for l in done)


def test_checking_the_store_adds_evidence_to_lessons_on_record_and_names_those_with_none(tmp_path):
    transcript, store = _workspace(tmp_path), tmp_path / "lessons.json"
    backed = lessons.propose(
        "python-flask-api", "a fix reverted for breaking tests that passed before it", "A rule.", 1, path=store)
    unbacked = lessons.propose("python-flask-api", "a failure no transcript records", "A rule.", 1, path=store)
    other_stack = lessons.propose(
        "node-http-api", "a fix reverted for breaking tests that passed before it", "A rule.", 1, path=store)

    without = lesson_distiller.check_the_evidence([(transcript, tmp_path)], path=store)

    assert [l["id"] for l in without] == [unbacked["id"], other_stack["id"]]
    assert [l["evidence_in"] for l in lessons.load(store) if l["id"] == backed["id"]] == [["run"]]
    assert len(lessons.load(store)) == 3, "a check proposes nothing new"
