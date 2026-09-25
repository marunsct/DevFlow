"""Render `docs/technical_specification.md` from the architect's decision.

The architect used to produce the specification twice: once as Markdown
written to disk, and once as the structured response the pipeline routes on.
The two were generated separately from the same understanding, and nothing
reconciled them - the same shape that let a 1 KB `docs/spec.md` sit beside a
51 KB `docs/technical_specification.md` on 

The cost is not only divergence. A full specification is roughly 40 KB of
prose; asking for it twice doubles the most expensive generation in the
pipeline. md`" - on three fresh conversations in a row,
each ending in a ~100,000 character message. It had spent itself on the
document and treated the schema as redundant, which from its side it was.

So the structured response is now the only thing it produces, and the document
is rendered from it. The schema's twelve fields are the document's sections, so
this is a formatting step rather than a translation.
"""

from __future__ import annotations

from typing import Any

#: Schema field -> heading, in the order a reader expects them.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("product_scope", "Product Scope"),
    ("component_boundaries", "Component Boundaries"),
    ("domain_model", "Domain Model"),
    ("api_and_event_contracts", "API and Event Contracts"),
    ("data_flows", "Data Flows"),
    ("security_and_privacy", "Security and Privacy"),
    ("reliability_and_observability", "Reliability and Observability"),
    ("testing", "Testing"),
    ("deployment", "Deployment"),
    ("acceptance_criteria", "Acceptance Criteria"),
    ("open_questions", "Open Questions"),
)

#: ADR field -> label. `title` becomes the heading, so it is not listed.
_ADR_FIELDS: tuple[tuple[str, str], ...] = (
    ("context", "Context"),
    ("alternatives", "Alternatives"),
    ("decision", "Decision"),
    ("rationale", "Rationale"),
    ("trade_offs", "Trade-offs"),
    ("consequences", "Consequences"),
    ("validation_evidence", "Validation evidence"),
)


def _as_lines(value: Any) -> list[str]:
    """One section's content as Markdown lines.

    Delegates to the general renderer so both share one behaviour - in
    particular the unpacking of JSON a model has put into a prose field, which
    `product_scope` arrived as on 
    """
    from app.agents.artifact_document import _value_lines

    return _value_lines(value)


def render_specification(specification: Any, product_name: str = "") -> str:
    """The Markdown a person reads, built from the decision the pipeline routes on."""
    title = f"Technical Specification — {product_name}" if product_name else "Technical Specification"
    parts: list[str] = [f"# {title}", ""]

    for field, heading in _SECTIONS:
        lines = _as_lines(getattr(specification, field, None))
        parts.append(f"## {heading}")
        # Said plainly rather than left blank: an empty required section is
        # something a reviewer should see, not something to hide.
        parts.extend(lines if lines else ["_Not specified._"])
        parts.append("")

    decisions = list(getattr(specification, "decisions", None) or [])
    parts.append("## Decisions (ADR)")
    if not decisions:
        parts.extend(["_No architecture decisions were recorded._", ""])
    else:
        parts.append("")
        for index, record in enumerate(decisions, 1):
            heading = str(getattr(record, "title", "") or f"Decision {index}").strip()
            parts.append(f"### ADR-{index:02d} — {heading}")
            for field, label in _ADR_FIELDS:
                lines = _as_lines(getattr(record, field, None))
                if not lines:
                    continue
                parts.append(f"**{label}:**")
                parts.extend(lines)
                parts.append("")
            parts.append("")

    parts.append(
        "<!-- Generated from the architect's structured specification. Editing "
        "this file does not change what the pipeline reads. -->"
    )
    return "\n".join(parts).rstrip() + "\n"


__all__ = ["render_specification"]
