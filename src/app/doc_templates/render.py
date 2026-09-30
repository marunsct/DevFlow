"""The template engine behind `app.doc_templates`: one environment, a few filters.

Filters, not logic, carry the formatting rules every template shares:

- `section`   any field as Markdown lines, or a stated placeholder when empty
- `bullets`   a list as `- item` lines, or a stated placeholder when empty
- `text`      one value on one line, or a stated placeholder when empty
- `cell`      one Markdown table cell: no pipe or newline can break the row
- `yesno`     a flag as "yes" / "no"
- `first_line` the first non-blank line of a value

An empty section always says so. A gap a reader should notice is not the same
as a gap that is hidden, and a heading with nothing under it reads as a
rendering fault.

Whitespace is normalised after rendering - trailing spaces removed, runs of
blank lines collapsed to one, a single final newline - so the document's
layout does not depend on how many newlines a model put inside a field.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from jinja2 import ChainableUndefined, Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).with_name("templates")

NOT_SPECIFIED = "_Not specified._"
NONE_RECORDED = "None recorded."


def _value_lines(value: Any) -> list[str]:
    """Any field as Markdown lines; shares the JSON-in-prose unpacking."""
    from app.agents.artifact_document import _value_lines as lines

    return lines(value)


def _section(value: Any, empty: str = NOT_SPECIFIED) -> str:
    lines = _value_lines(value)
    return "\n".join(lines) if lines else empty


def _bullets(items: Iterable[Any] | None, empty: str = NONE_RECORDED, numbered: bool = False) -> str:
    kept = [" ".join(str(item).split()) for item in (items or ()) if str(item).strip()]
    if not kept:
        return empty
    if numbered:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(kept, 1))
    return "\n".join(f"- {item}" for item in kept)


def _text(value: Any, empty: str = "not stated") -> str:
    flat = " ".join(str(value or "").split())
    return flat or empty


def _first_line(value: Any, empty: str = "") -> str:
    for line in str(value or "").splitlines():
        if line.strip():
            return " ".join(line.split())
    return empty


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip() or "-"


def _yesno(value: Any) -> str:
    return "yes" if value else "no"


_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    # Lenient on purpose. A document is written after a stage's outcome is
    # decided and must never be what fails it, so a value an object does not
    # carry renders as the section's placeholder. A template that forgets a
    # field is caught by `tests/test_document_templates.py` instead.
    undefined=ChainableUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,
)
_ENV.filters.update(
    section=_section, bullets=_bullets, text=_text, cell=_cell, yesno=_yesno,
    first_line=_first_line,
)


def _tidy(rendered: str) -> str:
    lines = [line.rstrip() for line in rendered.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


def render_document(name: str, **context: Any) -> str:
    """Render `templates/<name>.md.j2` with `context`."""
    return _tidy(_ENV.get_template(f"{name}.md.j2").render(**context))


def template_names() -> list[str]:
    """Every template this package holds, by name."""
    return sorted(path.name[: -len(".md.j2")] for path in TEMPLATE_DIR.glob("*.md.j2"))


__all__ = ["TEMPLATE_DIR", "render_document", "template_names"]
