"""The architect writes the specification once, not twice.

It used to produce the whole thing twice from one understanding: Markdown
written to `docs/technical_specification.md`, and the same content again as the
structured response the pipeline routes on. Nothing reconciled them - the shape
that let a 1 KB `docs/spec.md` sit beside a 51 KB
`docs/technical_specification.md` on one run.

The cost was not only divergence. Measured on one run: the architect wrote
the document, then reported in prose - "The technical specification has been
written to `docs/technical_specification.md`" - on three fresh conversations,
each ending in a ~100,000 character message, and the run failed. It had spent
itself on the document and treated the schema as redundant, which from where it
stood it was.
"""

from __future__ import annotations

from app.agents.principal_architect import (
    ArchitectureDecisionRecord,
    TechnicalSpecificationOutput,
)
from app.agents.specification_document import render_specification


def _spec(**overrides):
    base = dict(
        product_scope="A single-page to-do list.",
        component_boundaries=["UI layer", "Storage adapter"],
        testing=["Manual browser checks"],
    )
    base.update(overrides)
    return TechnicalSpecificationOutput(**base)


def test_every_section_reaches_the_document():
    document = render_specification(_spec(), "To-Do App")

    assert "# Technical Specification — To-Do App" in document
    assert "A single-page to-do list." in document
    assert "- UI layer" in document
    assert "- Manual browser checks" in document


def test_every_schema_field_has_a_heading():
    """A field with nowhere to go is content the document silently drops."""
    from app.agents.specification_document import _SECTIONS

    rendered = {field for field, _ in _SECTIONS} | {"decisions"}
    schema = set(TechnicalSpecificationOutput.model_fields)

    assert schema == rendered, f"unrendered fields: {schema - rendered}"


def test_an_empty_section_says_so_rather_than_vanishing():
    """A reviewer should see the gap, not an absence."""
    document = render_specification(_spec())

    assert "## Domain Model" in document
    assert "_Not specified._" in document


def test_decisions_render_as_numbered_adrs():
    spec = _spec(
        decisions=[
            ArchitectureDecisionRecord(
                title="Vanilla JS",
                context="The brief forbids dependencies",
                alternatives=["React"],
                decision="Use vanilla JS",
                rationale="The constraint is binding",
                trade_offs=["More manual DOM work"],
                consequences=["No build step"],
                validation_evidence="Brief, technical constraints",
            )
        ]
    )

    document = render_specification(spec)

    assert "### ADR-01 — Vanilla JS" in document
    assert "**Rationale:**" in document
    assert "The constraint is binding" in document


def test_no_decisions_is_stated_not_blank():
    assert "_No architecture decisions were recorded._" in render_specification(_spec())


def test_the_document_says_where_it_came_from():
    document = render_specification(_spec())

    assert "Generated from the architect's structured specification" in document
    assert "does not change what the pipeline reads" in document


def test_the_architect_is_not_told_to_write_the_document():
    from app.agents.principal_architect import _SYSTEM_PROMPT

    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "Do not write a specification document" in flat
    assert "produces the whole document twice" in flat
    assert "Write your technical specification to" not in flat


def test_the_reviewer_knows_remediations_are_field_changes():
    """Asking the architect to edit a file it no longer writes cannot converge."""
    from app.agents.architecture_reviewer import _SYSTEM_PROMPT

    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "The architect does not write the document" in flat
    assert "never an instruction to edit a file" in flat


def test_the_workflow_renders_it():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py").read_text()

    assert "render_specification(" in workflow
    assert '"docs/technical_specification.md"' in workflow
