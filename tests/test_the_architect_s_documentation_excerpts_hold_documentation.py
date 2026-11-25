"""The architect's documentation excerpts hold the libraries' documentation, not their landing pages' furniture; with
`DOCUMENTATION_EXCERPTS_BOUNDED` on, only what bears on the brief, bounded per library (LF.1471).

Measured on one medium run: the architect's "evidence for the chosen stack" was 19,354 characters in all 17 of its
calls, among them a README's "Gold Sponsors" list, logo and badge markup and "Join Discord", beside the version table
it was asked to cite. The pages and the brief here are that run's, captured from the architect's request.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.agents import research_brief

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAPTURED = json.loads((Path(__file__).parent / "captured" / "architect_stack_evidence.json").read_text("utf-8"))
STACK = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="React", database="PostgreSQL",
                        testing_framework="Playwright", additional_tools=["SQLAlchemy", "Alembic"])


def _notes(monkeypatch) -> str:
    from app.tools import docs, package_registry

    monkeypatch.setattr(package_registry, "enabled", lambda: False)
    monkeypatch.setattr(docs, "enabled", lambda: True)
    # The documentation pages as the reader returned them for that run (the network is the edge here).
    monkeypatch.setattr(docs, "read", lambda name, topic, ecosystem="": {"excerpt": CAPTURED["pages"].get(name, "")})
    return research_brief.research_notes(STACK, CAPTURED["brief"], None, workers=1)


def test_the_excerpts_hold_no_sponsor_list_badge_or_markup(monkeypatch):
    sent = CAPTURED["evidence_as_sent"]
    assert "### Gold Sponsors" in sent and "[![PyPI]" in sent and '<p align="center">' in sent

    notes = _notes(monkeypatch)

    assert "Sponsors" not in notes and "[![" not in notes and "<p align" not in notes and "<img" not in notes
    # The documentation itself stays: a page's prose and its code examples.
    assert "FastAPI is a modern, fast (high-performance), web framework" in notes
    assert "from playwright.sync_api import sync_playwright" in notes


def test_bounded_each_library_keeps_what_bears_on_the_brief_within_its_bound(monkeypatch):
    monkeypatch.setenv("DOCUMENTATION_EXCERPTS_BOUNDED", "on")

    notes = _notes(monkeypatch)
    pages = re.split(r"(?m)^### ", notes)[1:]

    assert pages and all(research_brief.BOUNDED_SAID in page.split("\n", 1)[0] for page in pages)
    assert all(len(page.split("\n", 1)[1]) <= research_brief.MOST_BOUNDED_CHARACTERS for page in pages)
    assert len(notes) < len(_notes_off(monkeypatch))


def _notes_off(monkeypatch) -> str:
    monkeypatch.setenv("DOCUMENTATION_EXCERPTS_BOUNDED", "off")
    return _notes(monkeypatch)


def test_off_by_default():
    assert research_brief.bounded_excerpts_switch.ON_BY_DEFAULT is False


def test_what_it_says_uses_none_of_the_banned_words():
    assert not BANNED.search(research_brief.BOUNDED_SAID + research_brief.bounded_excerpts_switch.explanation)
