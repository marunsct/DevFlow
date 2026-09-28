"""The stage that writes the specification, given the brief's own constraints.

`brief_constraints` already served the stage that picks the stack and the one
that reviews the specification. The stage that *writes* it had the whole
document under "Original uploaded documents" and not the constraints pulled out
of it - and that was not enough:

- one run's specification said "Backend: Express server"
- one run's said "Tests run with Node's built-in test runner (node --test)
  in a jsdom environment to simulate DOM interactions"
- one run's said "Use Node's built-in test runner (node --test) with jsdom
  for DOM simulation"

all against a brief reading "No external dependencies beyond basic
HTML/CSS/JS". The specialists that installed jsdom were building to spec. This
is where that choice is made, and the checks that catch it afterwards are
catching a decision taken here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.principal_architect import (
    build_architecture_request,
    build_architecture_revision_request,
)

BRIEF = """# Product Brief

## Technical Constraints
- Single-page application
- No external dependencies beyond basic HTML/CSS/JS
"""


@pytest.fixture
def document():
    return SimpleNamespace(
        text=BRIEF, source_type="markdown", truncated=False, truncation_note=""
    )


@pytest.fixture
def repository():
    return SimpleNamespace(branch="main", commit="abc123", root_path="/tmp")


def test_the_initial_request_quotes_the_constraints(document, repository):
    body = build_architecture_request(
        "intake", "tools", "stack", repository, document
    )["messages"][0]["content"]

    assert "No external dependencies beyond basic HTML/CSS/JS" in body
    assert "Technical constraints, quoted from the brief" in body


def test_the_constraints_come_before_the_derived_documents(document, repository):
    """A constraint read after three summaries of it has already lost."""
    body = build_architecture_request(
        "intake", "tools", "stack", repository, document
    )["messages"][0]["content"]

    assert body.index("quoted from the brief") < body.index("Approved product intake")


def test_a_revision_also_gets_them(document, repository):
    """An architect rewriting the specification is making the choice again."""
    body = build_architecture_revision_request(
        "previous spec", ["change this"], "intake", "tools", "stack", repository, document
    )["messages"][0]["content"]

    assert "No external dependencies beyond basic HTML/CSS/JS" in body


def test_a_brief_stating_no_constraints_adds_nothing(repository):
    plain = SimpleNamespace(
        text="# Brief\n\n## Overview\nBuild a thing.\n",
        source_type="markdown",
        truncated=False,
        truncation_note="",
    )

    body = build_architecture_request("intake", "tools", "stack", repository, plain)[
        "messages"
    ][0]["content"]

    assert "quoted from the brief" not in body
    assert "Approved product intake" in body


def test_the_constraint_block_never_raises():
    """An architect without this still writes a specification.

    The builder itself needs a real `DocumentContent` - it excerpts the text -
    so this is about the block added here, not about the request tolerating a
    garbage document, which it never promised to do.
    """
    from app.agents.principal_architect import _the_briefs_own_constraints

    assert _the_briefs_own_constraints(object()) == ""
    assert _the_briefs_own_constraints(None) == ""
    assert _the_briefs_own_constraints(SimpleNamespace(text=None)) == ""
