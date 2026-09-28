"""The gate that accepts a milestone reads the brief it is meant to satisfy.

One run completed. Its architecture review returned "approved" with no
findings, both security reviews "passed", and the milestone review raised one
blocking finding - a missing npm test script - then "accepted". What it
delivered was:

    simple-to-do-list-app/index.js            616 bytes, an Express server
    simple-to-do-list-app/app.test.js
    simple-to-do-list-app/index.test.js
    simple-to-do-list-app/package-lock.json   32,693 bytes

No HTML. No CSS. No front-end JavaScript. The brief's first requirement is
"Simple web-based interface with HTML/CSS/JavaScript"; its constraints are
"Single-page application" and "No external dependencies beyond basic
HTML/CSS/JS".

Every gate passed because every gate reviews the artifacts against each other
and against the milestone's own goal. The brief entered at the product manager
and was never read again.
"""

import pytest

from app.agents.brief_constraints import what_the_brief_asked_for_that_is_missing
from app.agents.milestone_reviewer import build_milestone_review_request

BRIEF = """# Product Brief: Simple To-Do List App

## Requirements
1. **User Interface**: Simple web-based interface with HTML/CSS/JavaScript

## Technical Constraints
- Single-page application
- No external dependencies beyond basic HTML/CSS/JS
- Should work in modern browsers
"""


def test_the_measured_product_is_reported_as_missing_its_interface():
    missing = what_the_brief_asked_for_that_is_missing(
        BRIEF, ["index.js", "app.test.js", "package-lock.json", "package.json"]
    )

    assert len(missing) == 1
    assert "contains no HTML file" in missing[0]


def test_a_product_with_a_page_is_silent():
    assert (
        what_the_brief_asked_for_that_is_missing(
            BRIEF, ["index.html", "main.js", "style.css"]
        )
        == []
    )


def test_a_page_with_no_stylesheet_is_noted_but_not_asserted():
    """An inline `<style>` is legitimate, so this asks rather than declares."""
    missing = what_the_brief_asked_for_that_is_missing(BRIEF, ["index.html", "main.js"])

    assert len(missing) == 1
    assert "carries its own `<style>`" in missing[0]


def test_a_brief_that_asks_for_no_page_is_silent():
    """A CLI tool has no HTML and that is correct."""
    assert (
        what_the_brief_asked_for_that_is_missing(
            "# Brief\n\nBuild a command line tool that reads stdin.", ["main.py"]
        )
        == []
    )


def test_an_empty_brief_is_silent():
    assert what_the_brief_asked_for_that_is_missing("", ["index.js"]) == []


@pytest.mark.parametrize(
    "phrase",
    ["web-based interface", "single-page", "in the browser", "HTML", "front-end"],
)
def test_the_phrases_that_mean_a_page_is_wanted(phrase):
    missing = what_the_brief_asked_for_that_is_missing(f"Build a {phrase} thing.", ["main.js"])

    assert missing and "no HTML file" in missing[0]


def test_the_reviewer_is_given_the_finding(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "index.js").write_text("import http from 'node:http';\n")
    (tmp_path / ".project-directory").write_text("app")

    content = build_milestone_review_request(
        "goal", [], "", "", str(tmp_path), None, BRIEF
    )["messages"][0]["content"]

    assert "contains no HTML file" in content
    assert "No external dependencies beyond basic HTML/CSS/JS" in content
    assert "not a reading of the brief" in content


def test_the_reviewer_without_a_brief_is_unchanged(tmp_path):
    content = build_milestone_review_request("goal", [], "", "", str(tmp_path))["messages"][0][
        "content"
    ]

    assert "The brief this product is measured against" not in content


def test_the_constraints_appear_even_when_nothing_is_missing(tmp_path):
    """A reviewer that can read them can catch what the fixed checks cannot."""
    project = tmp_path / "app"
    project.mkdir()
    (project / "index.html").write_text("<!DOCTYPE html><html></html>")
    (project / "style.css").write_text("body{}")
    (tmp_path / ".project-directory").write_text("app")

    content = build_milestone_review_request(
        "goal", [], "", "", str(tmp_path), None, BRIEF
    )["messages"][0]["content"]

    assert "No external dependencies beyond basic HTML/CSS/JS" in content
    assert "contains no HTML file" not in content
