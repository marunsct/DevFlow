"""The intake carries the brief's constraints even when the model omits them.

Run 0c5aabdb rendered `## Constraints / _Not specified._` for a brief with a
`## Technical Constraints` heading and four lines under it. The principal
architect writes the specification from the intake and never sees the brief, so
"Backend: Express server" went into a product whose brief says "No external
dependencies beyond basic HTML/CSS/JS" - correct work by both stages on what
they were given.
"""

from __future__ import annotations

from app.agents.product_manager import (
    ProductManagerOutput,
    with_the_constraints_the_brief_states,
)

BRIEF = """# Product Brief: Simple To-Do List App

## Overview
Build a basic to-do list application.

## Technical Constraints
- Single-page application
- No external dependencies beyond basic HTML/CSS/JS
- Maximum 500 lines of code
"""


def _intake(**kwargs) -> ProductManagerOutput:
    return ProductManagerOutput(product_name="To-Do List", **kwargs)


def test_an_empty_constraints_field_is_filled_from_the_brief():
    filled = with_the_constraints_the_brief_states(_intake(), BRIEF)
    assert "No external dependencies beyond basic HTML/CSS/JS" in filled.constraints
    assert "Single-page application" in filled.constraints
    assert "Maximum 500 lines of code" in filled.constraints


def test_what_the_model_found_is_kept_and_comes_first():
    model_found = "Must load in under one second"
    filled = with_the_constraints_the_brief_states(
        _intake(constraints=[model_found]), BRIEF
    )
    assert filled.constraints[0] == model_found
    assert "Single-page application" in filled.constraints


def test_a_constraint_the_model_already_stated_is_not_repeated():
    filled = with_the_constraints_the_brief_states(
        _intake(constraints=["single-page application"]), BRIEF
    )
    said = [c for c in filled.constraints if c.lower() == "single-page application"]
    assert len(said) == 1


def test_a_brief_with_no_constraints_leaves_the_output_alone():
    plain = "# Brief\n\n## Overview\nBuild a thing that does something.\n"
    original = _intake(constraints=["Only what the model found"])
    filled = with_the_constraints_the_brief_states(original, plain)
    assert filled.constraints == ["Only what the model found"]


def test_the_rendered_intake_no_longer_says_not_specified():
    from app.agents.artifact_document import render_artifact

    rendered = render_artifact(
        with_the_constraints_the_brief_states(_intake(), BRIEF),
        title="Product Intake",
    )
    constraints_section = rendered.split("## Constraints", 1)[1]
    assert "_Not specified._" not in constraints_section.split("##", 1)[0]
    assert "No external dependencies" in constraints_section
