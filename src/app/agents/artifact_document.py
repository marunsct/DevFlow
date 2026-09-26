"""Render any structured agent output as the Markdown document a person reads.

Seven agents used to produce their work twice: once as a document written to
`docs/`, and once as the structured response the pipeline routes on. The two
were generated separately from one understanding and nothing reconciled them.

That cost three things, all measured:

- **Divergence.** On run-0b55ad49 a 1 KB `docs/spec.md` sat beside a 51 KB
  `docs/technical_specification.md`; the reviewer read the thin one and blocked
  a sprint for detail that was in the other file.
- **Double generation.** The specification is ~40 KB of prose. Asking for it
  twice doubles the most expensive call in the pipeline.
- **Confusion about what "done" means.** On run-0edfcd33 the architect wrote
  the document and then reported in prose - "The technical specification has
  been written to `docs/technical_specification.md`" - on three fresh
  conversations, each ending in a ~100,000 character message, and the run
  failed. From where it stood the schema was redundant; it had already
  delivered the work.

So the structured response became the single source, and the document is
rendered from it. This renderer is general because the pattern was: every one
of these schemas is a flat set of sections, some holding nested records, and
`_SECTION_TITLES` only has to name the ones whose default heading reads badly.
"""

from __future__ import annotations

import json

from typing import Any

#: Headings that a mechanical title-case of the field name gets wrong.
_SECTION_TITLES: dict[str, str] = {
    "mvp_candidates": "MVP Candidates",
    "evidence_vs_assumptions": "Evidence vs Assumptions",
    "api_and_event_contracts": "API and Event Contracts",
    "adrs": "Decisions (ADR)",
    "technology_stack": "Selected Technology Stack",
    "queue_and_job_systems": "Queues and Job Systems",
    "ui_ux": "UI/UX",
}

#: Fields that name the document rather than forming a section of it.
_TITLE_FIELDS = ("product_name", "selected_sprint_goal")


def _heading(field: str) -> str:
    return _SECTION_TITLES.get(field) or field.replace("_", " ").strip().capitalize()


def _fields_of(value: Any) -> list[str]:
    """The declared field names of a pydantic model, from its class.

    Read from `type(value)` rather than the instance: Pydantic 2.11 deprecated
    the instance attribute, and reading it produced one warning per nested
    record - 218 across the test suite, enough to hide a real one.
    """
    return list(getattr(type(value), "model_fields", {}) or {})


def _is_record(value: Any) -> bool:
    """A nested pydantic-style model, rather than a scalar or a plain list."""
    return bool(_fields_of(value)) and hasattr(value, "model_dump")


def _record_lines(record: Any, depth: int = 0) -> list[str]:
    """One nested record as labelled lines, its first field as the sub-heading."""
    fields = _fields_of(record)
    if not fields:
        return [f"- {record}"]

    lines: list[str] = []
    first = str(getattr(record, fields[0], "") or "").strip()
    # A record whose first field is a short label - a role, a category - reads
    # badly as a heading on its own: seven tasks become seven "backend"
    # headings. Where a descriptive field follows, it joins the heading.
    descriptive = next(
        (
            f
            for f in fields[1:]
            if ("description" in f or "title" in f or "goal" in f or f == "name")
            and isinstance(getattr(record, f, None), str)
            and getattr(record, f).strip()
        ),
        None,
    )
    heading = first or "Item"
    if descriptive and len(first) <= 30:
        heading = f"{first} — {getattr(record, descriptive).strip()}" if first else getattr(record, descriptive).strip()
    lines.append(f"{'#' * (depth + 4)} {heading}")
    skip = {fields[0]} | ({descriptive} if descriptive and len(first) <= 30 else set())
    for field in fields[1:]:
        if field in skip:
            continue
        value = getattr(record, field, None)
        rendered = _value_lines(value, depth + 1)
        if not rendered:
            continue
        lines.append(f"**{_heading(field)}:**")
        lines.extend(rendered)
        lines.append("")
    return lines


def _json_in_a_prose_field(text: str) -> list[str] | None:
    """A string field holding JSON, rendered readably instead of as a blob.

    Models put structure into string fields. Measured on run-78804673, the
    architect's `product_scope` - a prose field - arrived as
    `{"in_scope": [...], "deferred_scope": [...]}`, and rendering it verbatim
    produced a single 1,200-character line no reader would read.

    The content is right; only its container is wrong. Unpacking it is better
    than dropping it and better than printing it raw, and the document is
    generated so there is no second copy to disagree with.
    """
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return None

    lines: list[str] = []
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            rendered = _value_lines(value)
            if not rendered:
                continue
            lines.append(f"**{_heading(str(key))}:**")
            lines.extend(rendered)
            lines.append("")
        return lines or None
    if isinstance(parsed, list):
        return [f"- {str(item).strip()}" for item in parsed if str(item).strip()] or None
    return None


def _value_lines(value: Any, depth: int = 0) -> list[str]:
    """Any field's value as Markdown lines. Empty when there is nothing to say."""
    if value is None:
        return []
    if isinstance(value, bool):
        return ["yes" if value else "no"]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        if not value.strip():
            return []
        unpacked = _json_in_a_prose_field(value)
        return unpacked if unpacked is not None else [value.strip()]
    if _is_record(value):
        return _record_lines(value, depth)
    if isinstance(value, (list, tuple)):
        lines: list[str] = []
        for item in value:
            if _is_record(item):
                lines.extend(_record_lines(item, depth))
            elif str(item).strip():
                lines.append(f"- {str(item).strip()}")
        return lines
    return [str(value)]


def render_artifact(output: Any, *, title: str, subtitle: str = "") -> str:
    """The Markdown document for one structured agent output.

    Every field becomes a section, in schema order, so a reader sees the same
    shape the pipeline does. An empty section says so rather than vanishing: a
    gap a reviewer should notice is not the same as a gap that is hidden.
    """
    fields = _fields_of(output)

    name = ""
    for candidate in _TITLE_FIELDS:
        if candidate in fields and str(getattr(output, candidate, "") or "").strip():
            name = str(getattr(output, candidate)).strip()
            break

    parts = [f"# {title}" + (f" — {name}" if name else ""), ""]
    if subtitle:
        parts.extend([subtitle, ""])

    for field in fields:
        if field in _TITLE_FIELDS and name:
            continue
        lines = _value_lines(getattr(output, field, None))
        parts.append(f"## {_heading(field)}")
        parts.extend(lines if lines else ["_Not specified._"])
        parts.append("")

    parts.append(
        "<!-- Generated from this stage's structured response. Editing this file "
        "does not change what the pipeline reads. -->"
    )
    return "\n".join(parts).rstrip() + "\n"


__all__ = ["render_artifact"]
