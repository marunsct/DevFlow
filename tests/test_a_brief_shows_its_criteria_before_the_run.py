"""A brief shows the acceptance criteria it gives a run before the run starts (plan BG.10).

The start page said nothing of what a run would be held to until the run had
written its suite, an hour in. The numbering is deterministic - no model call
- so the page shows it while the brief is being written.
"""

from __future__ import annotations

BRIEF = """# Notes

## Features
- Add a note with a title
- List every note, newest first
- Delete a note

## Out of scope
- Sharing notes
"""


def test_the_brief_s_criteria_as_the_run_will_number_them(client):
    body = client.post("/api/runs/preview", json={"brief": BRIEF}).json()

    assert body["from_brief"] is True
    assert [(c["id"], c["text"]) for c in body["criteria"]] == [
        ("AC-1", "Add a note with a title"), ("AC-2", "List every note, newest first"), ("AC-3", "Delete a note"),
    ]


def test_a_brief_that_lists_too_few_says_the_intake_will_name_them(client):
    body = client.post("/api/runs/preview", json={"brief": "Build a notes app people like."}).json()
    assert body == {"criteria": [], "from_brief": False, "without_an_interface_line": [], "vague_phrases": []}
