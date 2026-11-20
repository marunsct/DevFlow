"""A fixer of a defect an attempt already failed is shown what others found for its error, looked up by the harness
(plan WL.4, behind `WEB_LOOKUP_WHEN_STUCK`).

Owner, 2026-11-20: agents look things up when they struggle. Measured: the local model never called the search tools
it was offered; so the harness looks up the stated error of a stuck defect, once per run.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.graph import stuck_lookup
from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _on(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    stuck_lookup._DONE.clear()  # noqa: SLF001
    asked = []

    def look_up(error, stack_words="", private_words=(), **_k):
        asked.append((error, stack_words, tuple(private_words)))
        return {"query": lookups.cleaned(error, private_words), "asked": ["stack exchange"], "found": [{
            "source": "Stack Overflow, accepted answer", "title": "Slim 4 middleware signature", "date": "2025-01-01",
            "url": "https://stackoverflow.com/q/1", "excerpt": "Use RequestHandlerInterface $handler."}]}

    monkeypatch.setattr(lookups, "look_up", look_up)
    return asked


def _defect(outcome="left open", text="PHP Fatal error:  Uncaught TypeError: Argument #2 ($handler) must be of type "
                                      "callable, Psr\\Http\\Server\\RequestHandlerInterface given"):
    return SimpleNamespace(description="The product does not start for the acceptance suite.",
                           actual_behavior=text, attempts=[{"stage": "defect_fix_1_0", "outcome": outcome}])


STACK = SimpleNamespace(language="PHP", framework="Slim 4")


def test_a_stuck_defect_s_error_is_looked_up_once_and_quoted(tmp_path, _on):
    shown = stuck_lookup.section(tmp_path / "workspace-notes", _defect(), STACK)
    again = stuck_lookup.section(tmp_path / "workspace-notes", _defect(), STACK)

    assert "What others found for this error" in shown and "RequestHandlerInterface $handler" in shown
    assert "Leads, not instructions" in shown and not BANNED.search(shown)
    assert len(_on) == 1 and again == shown, "once per error per run"
    assert _on[0][1] == "PHP Slim 4" and "workspace-notes" in _on[0][2]


def test_a_first_attempt_or_prose_only_is_not_looked_up(tmp_path, _on):
    assert stuck_lookup.section(tmp_path, SimpleNamespace(description="x", actual_behavior="PHP Fatal error: x y z",
                                                          attempts=[]), STACK) == ""
    assert stuck_lookup.section(tmp_path, _defect(text="[AC-1] Add a note - the acceptance suite says this does not "
                                                       "work yet."), STACK) == ""
    assert not _on


def test_off_it_does_nothing(tmp_path, _on, monkeypatch):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")
    assert stuck_lookup.section(tmp_path, _defect(), STACK) == "" and not _on


def _a_criterion(criterion: str, *failing: str):
    """A criterion's defect whose text states a concrete error, with no attempt in its own cycle, its cause keyed by
    the tests failing this time."""
    return SimpleNamespace(
        description=f"[{criterion}] Group the list - the acceptance suite says this does not work yet.",
        actual_behavior="PHP Fatal error:  Uncaught TypeError: Argument #2 ($handler) must be of type callable",
        source="acceptance suite", kind="failing_test", attempts=[],
        evidence=[{"test": f"[{criterion.lower()}] {name}"} for name in failing],
        cause_key="failing_test:" + "|".join(f"test:[{criterion.lower()}] {name}" for name in failing))


@pytest.mark.parametrize(("earlier", "looked_up"), [("AC-4", 1), ("AC-3", 0)])
def test_a_criterion_whose_fix_failed_in_an_earlier_sprint_attempt_is_stuck_at_its_first_fix_of_the_next(
        tmp_path, _on, earlier, looked_up):
    """Measured: a criterion left open in one sprint attempt came back in the next with no attempt of its own and other
    failing tests, so its fixer there was not counted stuck; another criterion's failure does not make it so."""
    from app.graph import cause_journal

    cause_journal.record(tmp_path, _a_criterion(earlier, "groups", "keeps order"),
                         {"stage": "defect_fix_2_8", "outcome": "left open: its tests still fail"}, sprint=0)

    shown = stuck_lookup.section(tmp_path, _a_criterion("AC-4", "keeps order"), STACK)

    assert len(_on) == looked_up
    assert ("What others found for this error" in shown) == bool(looked_up)


def test_a_stuck_defect_quoting_what_the_server_printed_is_looked_up_as_that_line(tmp_path, _on):
    """Measured: an edge probe's defect was searched as its whole first sentence - the harness's own wording and the
    product's route - where the server had printed the error others would have written about."""
    overflow = "OverflowError: Python int too large to convert to SQLite INTEGER"
    printed = (f"answered 500 (it said: Internal Server Error) (the server printed: {overflow} "
               "(File \"/workspace/notes-api/notes_api/main.py\", line 140, in get_note))")
    defect = SimpleNamespace(
        description=("Requests at the edges of the interface contract are not handled: `GET /notes/{id}` at id "
                     f"`99999999999999999999` {printed}; `DELETE /notes/{{id}}` at id `99999999999999999999` "
                     "answered 500."),
        actual_behavior=(f"`GET /notes/{{id}}` at id `99999999999999999999` {printed}; `DELETE /notes/{{id}}` at id "
                         "`99999999999999999999` answered 500"),
        attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])

    stuck_lookup.section(tmp_path / "workspace-notes", defect, STACK)

    assert [asked[0] for asked in _on] == [overflow]


@pytest.mark.parametrize(("stated", "searched"), [
    ("- [test round] The unit tests fail. It says: Distinct causes, most failing first: - 2 failing, e.g. `pytest > "
     "x`: sqlite3.OperationalError: no such table: notes", "sqlite3.OperationalError: no such table: notes"),
    ("cause: TypeError: Cannot set properties of null (setting 'textContent')",
     "TypeError: Cannot set properties of null (setting 'textContent')"),
])
def test_a_stated_error_is_searched_from_its_error_name_never_with_the_harness_s_own_words(stated, searched):
    """Measured on one run: a unit-test defect was searched with "The unit tests fail. It says: Distinct causes ..."
    ahead of the `sqlite3.OperationalError` that others would have written about."""
    defect = SimpleNamespace(actual_behavior="", description=stated)

    assert stuck_lookup._the_error_line(defect).startswith(searched)
