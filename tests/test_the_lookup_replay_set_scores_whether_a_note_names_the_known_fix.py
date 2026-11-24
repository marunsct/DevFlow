"""A replay set of past stuck defects with their known fixes scores the stuck lookup with no model run: does the note
a fixer would be shown name the fix (plan HK.4, LF.1296).

Measured before it: whether a lookup helped could be judged only on live runs (2 of 9 looked-up defects fixed
afterwards), one run at a time, with the model's own work mixed in; a rebuilt lookup had nothing fixed to be scored on.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.graph import stuck_lookup
from app.tools import lookups

ROOT = Path(__file__).resolve().parents[1]
REPLAY = json.loads((ROOT / "benchmarks" / "lookup-replay.json").read_text(encoding="utf-8"))
A_RUN_ID = re.compile(r"\brun-[0-9a-f]{8}\b")


def _scorer():
    spec = importlib.util.spec_from_file_location("replay_lookups", ROOT / "scripts" / "loop" / "replay_lookups.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", REPLAY["cases"], ids=lambda case: case["id"])
def test_each_case_states_its_error_and_patterns_its_own_line_does_not_already_hold(case):
    """A pattern the error line itself holds would score every note quoting the question as naming the fix."""
    assert case["error"].strip() and case["fix"].strip() and case["language"].strip() and case["measured_in"]
    searched = f"{case['error']} {case['language']} {case['framework']}"
    assert [p for p in case["names_the_fix"] if re.search(p, searched, re.I)] == []
    assert [p for p in case["names_the_fix"] if re.search(p, case["fix"], re.I)], "the fix as written is named"


def test_the_set_holds_fifteen_to_twenty_five_distinct_cases_from_several_languages_and_no_run_id():
    cases = REPLAY["cases"]

    assert 15 <= len(cases) <= 25 and len({case["id"] for case in cases}) == len(cases)
    assert len({case["language"] for case in cases}) >= 5
    assert sum(1 for case in cases if case["public"]) >= 15
    assert not A_RUN_ID.search(json.dumps(REPLAY))


def test_a_note_naming_the_known_fix_scores_and_one_quoting_only_the_question_does_not():
    scorer = _scorer()
    cases = [{"id": "pool", "public": True, "error": "error[E0432]: unresolved import `sqlx::SqlitePoolOptions`",
              "names_the_fix": [r"sqlite::SqlitePoolOptions"]},
             {"id": "context", "public": True, "error": "RuntimeError: Working outside of application context.",
              "names_the_fix": [r"app_context\(\)"]},
             {"id": "silent", "public": False, "error": "ERROR: Exception in ASGI application",
              "names_the_fix": [r"create_all"]}]
    notes = {"pool": "- Stack Overflow: use sqlx::sqlite::SqlitePoolOptions instead",
             "context": "- GitHub issue: RuntimeError: Working outside of application context. Same here.",
             "silent": ""}
    waits: list[float] = []

    scored = scorer.score(cases, lambda case: notes[case["id"]], pace=3, sleep=waits.append)
    lines = scorer.report(scored, 0.6)

    assert [bool(s["named"]) for s in scored] == [True, False, False]
    assert lines[0] == "lookup replay: 1 of 2 (50%) public cases name the known fix; target 60% - not met"
    assert "not named (1 lead(s))" in lines[3] and "nothing found" in lines[4] and "[no public cause]" in lines[4]
    assert waits == [3, 3], "paced between cases, not before the first"


def test_a_case_whose_lookup_raises_is_scored_not_named_and_the_rest_go_on():
    scorer = _scorer()
    cases = [{"id": "a", "error": "x", "names_the_fix": ["y"]}, {"id": "b", "error": "x", "names_the_fix": ["y"]}]

    def look_up(case):
        if case["id"] == "a":
            raise TimeoutError("read timed out")
        return "- y"

    scored = scorer.score(cases, look_up)

    assert scored[0]["named"] == "" and "TimeoutError" in scored[0]["failed"] and scored[1]["named"] == "y"


def test_the_fixer_s_path_searches_the_case_s_error_with_its_stack(monkeypatch, tmp_path):
    """Through the stuck lookup a fixer gets (its public function), as a defect a fix left open."""
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    asked = []

    def look_up(error, stack_words="", private_words=(), **_k):  # the network's edge
        asked.append((error, stack_words))
        return {"query": error, "asked": ["stack exchange"], "found": [{
            "source": "Stack Overflow, accepted answer", "title": "t", "date": "2024-01-01",
            "url": "https://stackoverflow.com/q/1", "excerpt": "Wrap it in with app.app_context(): first."}]}

    monkeypatch.setattr(lookups, "look_up", look_up)
    stuck_lookup._DONE.clear()  # noqa: SLF001
    case = next(case for case in REPLAY["cases"] if case["id"] == "work-outside-the-application-context")

    note = _scorer().through_the_fixer(case)

    assert asked == [("RuntimeError: Working outside of application context.", "Python Flask")]
    assert _scorer().names_the_fix(case, note)
