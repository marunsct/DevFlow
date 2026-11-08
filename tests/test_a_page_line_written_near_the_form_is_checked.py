"""A page line written near the contract's form is read by its quoted name and a known role, never by a guess.

Over 274 scored runs, 87 carried page lines no check was compiled from: a file after the path, attributes after the
name, the element for its role, no path, single quotes. 54 of 89 such lines are read now; a selector, several
elements on one line, or a word that is no role stay unread, so no check is ever compiled with a role the page
check cannot ask for.
"""
from __future__ import annotations

import pytest

from app.acceptance import interface_contract


def _one(line: str):
    checks, unreadable = interface_contract.parse([line])
    return (checks[0] if checks else None), unreadable


@pytest.mark.parametrize(("line", "path", "role", "name"), [
    ('AC-1 page / index.html textbox "Title"', "/", "textbox", "Title"),
    ('AC-1 page / form input "Title" type="text"', "/", "textbox", "Title"),
    ('AC-2 page / input[aria-label="Filter by tag"] required', "/", "textbox", "Filter by tag"),
    ('AC-6 page textarea "Description"', "/", "textbox", "Description"),
    ("AC-5 page / index.html button 'Active'", "/", "button", "Active"),
    ('AC-3 page /index.html checkbox "Done"', "/index.html", "checkbox", "Done"),
    ('AC-4 page / index.html a "Docs" target="_blank"', "/", "link", "Docs"),
])
def test_a_line_near_the_form_becomes_a_page_check(line, path, role, name):
    check, unreadable = _one(line)
    assert unreadable == []
    assert (check.kind, check.path, check.role, check.name) == ("page", path, role, name)
    assert check.line == line, "the line is kept as written, for the release to name"


@pytest.mark.parametrize("line", [
    'AC-9 page / a[href="https://example.com"] text "Example Title"',
    "AC-11 page / div.bookmark-list",
    "AC-6 page / form element exists",
    'AC-2 page /index.html input[type=\'checkbox\'] "Done"',
    "AC-5 page /index.html button 'All' button 'Active' button 'Completed'",
    'AC-7 page / index.html banner-text "Saved" hidden',
    'AC-8 page / textbox "Title" "Body"',
])
def test_a_selector_several_elements_or_no_known_role_stay_unread(line):
    check, unreadable = _one(line)
    assert check is None and unreadable == [" ".join(line.split())]


def test_the_strict_form_is_read_as_before():
    check, _ = _one('AC-1 page /notes textarea "Body"')
    assert (check.path, check.role, check.name) == ("/notes", "textbox", "Body")
