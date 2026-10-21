"""How much a brief leaves the run to guess is counted at preview, before the run starts (plan IN.2)."""

from __future__ import annotations

from pathlib import Path

from app.acceptance.ambiguity import criteria_without_an_interface_line, interface_lines, vague_phrases
from app.acceptance.criteria import number

ROOT = Path(__file__).resolve().parent.parent

BRIEF = """# Notes
## Requirements
- Add a note with a title
- Search notes by word
- Export everything as a backup
## Interface
- `POST /notes` with `{"title": ...}` answers 201 with the note.
- `GET /notes?q=word` answers 200 with the notes whose title has the word.
## Constraints
- A modern, user-friendly design that works properly
"""


def test_a_criterion_no_interface_line_speaks_to_is_named():
    criteria = number(BRIEF)

    assert [c.text for c in criteria][:3] == ["Add a note with a title", "Search notes by word", "Export everything as a backup"]
    assert criteria_without_an_interface_line(BRIEF, criteria) == ["AC-3"]
    assert len(interface_lines(BRIEF)) == 2


def test_a_brief_with_no_interface_section_leaves_every_criterion_to_a_guess():
    brief = (ROOT / "tests" / "brief_medium.md").read_text()
    criteria = number(brief)
    assert len(criteria_without_an_interface_line(brief, criteria)) == len(criteria)


def test_vague_phrases_are_listed_once_each():
    assert vague_phrases(BRIEF) == ["modern", "user-friendly", "properly"]


def test_the_preview_route_answers_them(client):
    body = client.post("/api/runs/preview", json={"brief": BRIEF}).json()
    assert body["without_an_interface_line"] == ["AC-3"] and body["vague_phrases"] == ["modern", "user-friendly", "properly"]
