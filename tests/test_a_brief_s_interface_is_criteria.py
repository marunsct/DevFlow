"""A brief's interface section is acceptance criteria, line by line.

It says what the product shows, what each control is called and what it
refuses, and it is what the customer checks. It was not numbered: one run's
brief said "A task cannot be added without a title" there, QA's test of it was
refused as naming no criterion, the product disabled its add control instead,
and the customer's check timed out on it.
"""

from __future__ import annotations

from app.acceptance.criteria import from_brief, number

BRIEF = """# Product Brief: Notes

## Features
- Keep a note

## Interface
- A text field labelled "Name" and a button named "Keep".
- A note cannot be kept without a name.
- The service's JSON interface:
  - `GET /notes` answers 200 with every note.
  - `DELETE /notes/{id}` answers 204, or 404.

## Interface constraints
- Under 500 lines.
"""


def test_each_line_of_the_interface_is_a_criterion_in_the_brief_s_order() -> None:
    assert from_brief(BRIEF) == [
        "Keep a note",
        'A text field labelled "Name" and a button named "Keep"',
        "A note cannot be kept without a name",
        "GET /notes answers 200 with every note",
        "DELETE /notes/{id} answers 204, or 404",
    ]


def test_a_line_that_heads_a_list_is_not_one() -> None:
    assert not any(text.endswith(":") or "JSON interface" in text for text in from_brief(BRIEF))


def test_they_are_numbered_with_the_rest() -> None:
    assert [c.id for c in number(BRIEF)] == ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"]
