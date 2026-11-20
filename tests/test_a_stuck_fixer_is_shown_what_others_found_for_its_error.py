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
