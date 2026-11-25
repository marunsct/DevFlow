"""Every fixer shown says what became of its lookup (FX.11), and a library's error is looked up for its first fixer
behind `LOOKUP_AT_FIRST_SIGHT` (FX.9).

Measured on a medium run: none of eight fixer briefs had an error line, so every lookup returned at its gates and
nothing said which; the audit printed "not reached". The one library error the run met -
`'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`, raised from the installed SQLAlchemy - waited for a
failed fix that never came, where a search answers it in seconds.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.graph import stuck_lookup, stuck_research
from app.observability import lookup_notes, transcript
from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(language="Python", framework="FastAPI")
LIBRARY_ERROR = "AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'"
#: What a test runner printed for it: the error, then the installed library's frame it was raised in.
LIBRARY_TRACE = (
    "The unit tests fail at setup.\n"
    "visitor = <SQLiteTypeCompiler object at 0x7f76399160c0>\n"
    f"E           {LIBRARY_ERROR}. Did you mean: 'visit_REAL'?\n\n"
    ".venv/lib/python3.12/site-packages/sqlalchemy/sql/visitors.py:124: AttributeError\n")


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Stuck lookups on for the run, the lookup sources stubbed at the network's edge; yields the asked queries and a
    reader of the run's ledger."""
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.delenv("LOOKUP_AT_FIRST_SIGHT", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-gates")
    monkeypatch.setattr(lookups, "_get", lambda *a, **k: (404, "", {}))
    asked: list[str] = []
    answer = {"found": [{"source": "Stack Overflow, accepted answer", "title": "ARRAY on SQLite", "date": "2025-01-01",
                         "url": "https://stackoverflow.com/q/1", "excerpt": "SQLite has no ARRAY; use JSON."}]}

    def look_up(error, stack_words="", private_words=(), **_k):
        asked.append(error)
        return {"query": error, "asked": ["stack exchange"], **answer}

    monkeypatch.setattr(lookups, "look_up", look_up)
    yield SimpleNamespace(
        asked=asked, answer=answer,
        gates=lambda: [r for r in transcript.read_transcript("run-gates")
                       if r.get("kind") == "defect" and r.get("event") == lookup_notes.GATE])


def _defect(text: str, *, stuck: bool = False, description: str = "Registration answers 500") -> SimpleNamespace:
    return SimpleNamespace(description=description, actual_behavior=text, source="test round", owner="backend",
                           attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}] if stuck else [])


def _for_a_fixer(root, defect) -> str:
    return stuck_lookup.for_a_fixer(root, defect, [defect], STACK, round_=1, stage_name="defect_fix_1_0")


# --- FX.11: one record per fixer, naming the gate ---------------------------------------------------------------------

@pytest.mark.parametrize(("defect", "gate", "trigger"), [
    (_defect("Expected: 201\nReceived: 500"), "not stuck", "T1 stuck"),
    (_defect("Expected: 201\nReceived: 500", stuck=True), "no error line", "T1 stuck"),
    (_defect(f"the server printed: {LIBRARY_ERROR}", stuck=True), "looked up", "T1 stuck"),
])
def test_each_fixer_shown_leaves_one_record_of_its_lookup_or_the_gate_that_stopped_it(tmp_path, run, defect, gate,
                                                                                     trigger):
    _for_a_fixer(tmp_path / "workspace", defect)

    records = run.gates()
    assert [(r["gate"], r["trigger"]) for r in records] == [(gate, trigger)]
    assert records[0]["stage"] == "defect_fix_1_0"


def test_with_stuck_lookups_off_for_the_run_the_record_says_so(tmp_path, run, monkeypatch):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")

    _for_a_fixer(tmp_path, _defect(f"the server printed: {LIBRARY_ERROR}", stuck=True))

    assert [r["gate"] for r in run.gates()] == ["switched off"] and not run.asked


def test_a_search_that_found_nothing_is_told_apart_from_one_refused(tmp_path, run):
    run.answer.update(found=[])
    _for_a_fixer(tmp_path / "a", _defect(f"the server printed: {LIBRARY_ERROR}", stuck=True))
    run.answer.update(refused=["stack exchange"])
    _for_a_fixer(tmp_path / "b", _defect("the server printed: KeyError: 'owner_id'", stuck=True))

    assert [r["gate"] for r in run.gates()] == ["nothing found", "refused"]


def test_the_effects_report_counts_fixers_by_the_gate_that_stopped_their_lookup():
    records = [{"kind": "defect", "defect_id": f"d{n}", "event": "lookup gate", "gate": gate, "trigger": trigger}
               for n, (gate, trigger) in enumerate([("not stuck", "T1 stuck"), ("not stuck", "T1 stuck"),
                                                     ("no error line", "T1 stuck"), ("looked up", "T4 first sight")])]

    line = lookup_notes.gate_lines(records)[0]

    assert line.split()[0] == "4"
    assert "not stuck 2" in line and "no error line 1" in line and "looked up 1 (T4 first sight 1)" in line
    assert "not reached" in lookup_notes.gate_lines([])[0]


# --- FX.9: a library's error looked up at first sight ------------------------------------------------------------------

def test_a_library_s_error_is_looked_up_for_the_defect_s_first_fixer_with_first_sight_on(tmp_path, run, monkeypatch):
    monkeypatch.setenv("LOOKUP_AT_FIRST_SIGHT", "on")

    shown = _for_a_fixer(tmp_path, _defect(LIBRARY_TRACE))

    assert run.asked and "'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'" in run.asked[0]
    assert "installed package `sqlalchemy`" in shown and "SQLite has no ARRAY" in shown
    assert not BANNED.search(shown)
    assert [(r["gate"], r["trigger"]) for r in run.gates()] == [("looked up", "T4 first sight")]


def test_off_a_library_s_error_waits_for_a_failed_fix_as_before(tmp_path, run):
    shown = _for_a_fixer(tmp_path, _defect(LIBRARY_TRACE))

    assert shown == "" and not run.asked
    assert [r["gate"] for r in run.gates()] == ["not stuck"]


def test_an_error_raised_in_the_product_s_own_code_is_not_looked_up_at_first_sight(tmp_path, run, monkeypatch):
    monkeypatch.setenv("LOOKUP_AT_FIRST_SIGHT", "on")
    own = ('Traceback (most recent call last):\n  File "/workspace/app/routes/auth.py", line 99, in register\n'
           "KeyError: 'owner_id'\n")

    assert _for_a_fixer(tmp_path, _defect(own)) == "" and not run.asked


def test_a_library_s_error_met_again_by_another_defect_is_asked_once_in_the_run(tmp_path, run, monkeypatch):
    monkeypatch.setenv("LOOKUP_AT_FIRST_SIGHT", "on")

    first = _for_a_fixer(tmp_path, _defect(LIBRARY_TRACE))
    second = _for_a_fixer(tmp_path, _defect(LIBRARY_TRACE, description="Tables are not created"))

    assert len(run.asked) == 1 and second == first


@pytest.mark.parametrize(("error", "trace", "named"), [
    # Node: the error first, its innermost frame right after; the test runner's frame further down.
    ("TypeError: Cannot read properties of undefined (reading 'raw')",
     "TypeError: Cannot read properties of undefined (reading 'raw')\n"
     "    at parse (/workspace/svc/node_modules/hono/dist/request.js:41:12)\n"
     "    at handler (/workspace/svc/src/app.ts:12:5)\n"
     "    at run (/workspace/svc/node_modules/vitest/dist/runner.js:900:3)\n", ("hono", "npm")),
    # Python's own traceback: frames first, the innermost one just above the error.
    ("ValueError: password cannot be longer than 72 bytes",
     'Traceback (most recent call last):\n  File "/workspace/app/auth.py", line 10, in hash_it\n'
     '  File "/workspace/.venv/lib/python3.12/site-packages/bcrypt/__init__.py", line 80, in hashpw\n'
     "ValueError: password cannot be longer than 72 bytes\n", ("bcrypt", "pypi")),
    # No frame of an installed package: the product's own error.
    ("KeyError: 'owner_id'", 'File "/workspace/app/routes/auth.py", line 99, in register\nKeyError: \'owner_id\'\n',
     ("", "")),
])
def test_the_installed_package_an_error_comes_from_is_the_one_of_its_innermost_frame(tmp_path, error, trace, named):
    assert stuck_research.installed_package_named(tmp_path, error, trace) == named


def test_an_error_line_that_writes_one_of_the_project_s_packages_names_it(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "dependency-gate.json").write_text(json.dumps({
        "pypi:SQLAlchemy": {"verdict": "allowed"}, "pypi:fastapi": {"verdict": "allowed"}}))

    named = stuck_research.installed_package_named(
        tmp_path, "sqlalchemy.exc.InvalidRequestError: Could not determine join condition between parent/child")

    assert named == ("SQLAlchemy", "pypi")


def test_the_first_sight_note_names_no_banned_words():
    assert not BANNED.search(stuck_lookup.FIRST_SIGHT_SAYS.format(library="somelib"))
