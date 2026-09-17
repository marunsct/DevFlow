"""The builders' own words, which were recorded and never read.

`specialist_outputs` is consumed for `changed_files` and nothing else, so
`blockers`, `risks` and `decisions` were written into state and discarded -
while the workflow-document refusal told agents, every time it fired, that
"those reach the workflow and the next stage". That was not true.

The content is not incidental. Across the stored transcripts the fields hold,
among others:

    blockers:  "Test suite app.test.mjs fails because it imports named exports
                from app.js but the file no longer provides them"
    risks:     "Potential need for jsdom to mock DOM in tests, which would
                introduce an external dependency"
    decisions: "Removed ES module exports and added window.todoApp global object"

The module conflict, the forbidden dependency and the change that broke a
suite - each named by the specialist that did it, at the moment it happened.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.milestone_reviewer import (
    MAX_REPORTED_PER_KIND,
    build_milestone_review_request,
    what_the_specialists_reported,
)


def _output(**kwargs) -> SimpleNamespace:
    base = {"blockers": [], "risks": [], "decisions": []}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_a_blocker_reaches_the_reviewer():
    outputs = {"backend": _output(blockers=["app.js no longer provides named exports"])}

    assert "no longer provides named exports" in what_the_specialists_reported(outputs)


def test_a_risk_reaches_the_reviewer():
    outputs = {"testing": _output(risks=["Potential need for jsdom"])}

    assert "Potential need for jsdom" in what_the_specialists_reported(outputs)


def test_a_decision_reaches_the_reviewer():
    outputs = {"backend": _output(decisions=["Removed ES module exports"])}

    assert "Removed ES module exports" in what_the_specialists_reported(outputs)


def test_each_line_names_the_role_that_said_it():
    outputs = {"ui_ux": _output(blockers=["the page has no script tag"])}

    assert "[ui_ux]" in what_the_specialists_reported(outputs)


def test_it_says_these_are_the_builders_words():
    """So the reviewer weighs them as testimony, not as another file summary."""
    outputs = {"backend": _output(blockers=["x"])}

    note = what_the_specialists_reported(outputs)
    assert "builders' own words" in note
    assert "A blocker nobody resolved is still a blocker" in note


def test_nothing_reported_produces_nothing():
    assert what_the_specialists_reported({"backend": _output()}) == ""
    assert what_the_specialists_reported({}) == ""
    assert what_the_specialists_reported(None) == ""


def test_a_flood_is_trimmed():
    outputs = {"backend": _output(blockers=[f"blocker {i}" for i in range(20)])}

    note = what_the_specialists_reported(outputs)

    assert note.count("- [backend]") == MAX_REPORTED_PER_KIND


def test_an_output_of_an_unexpected_shape_is_survivable():
    """A reviewer without this still reviews."""
    assert what_the_specialists_reported({"odd": object()}) == ""


def test_the_request_carries_it(tmp_path):
    outputs = {"backend": _output(blockers=["app.js no longer provides named exports"])}

    body = build_milestone_review_request(
        "goal", ["app.js"], "tests pass", "none", str(tmp_path), None, "", outputs
    )["messages"][0]["content"]

    assert "What the specialists reported while building this" in body
    assert "no longer provides named exports" in body


def test_the_request_is_unchanged_when_there_is_nothing_to_report(tmp_path):
    body = build_milestone_review_request(
        "goal", ["app.js"], "tests pass", "none", str(tmp_path), None, "", {}
    )["messages"][0]["content"]

    assert "What the specialists reported" not in body
    assert "Milestone goal under review" in body
