"""The product's API, as the specification decides it, for whoever writes its tests.

A test written against a guessed shape fails a right product: one run's tests
asserted field names the specification never used, and the disputes that
followed rewrote the suite to match the code instead. The test writers were
given the specification through the project memory, and a large specification
is held there only as its outline - measured on a medium brief, 71,537
characters, of which the acceptance author saw the headings and none of the
endpoints, data shapes or error messages. So the parts a test is written
against are handed over whole, always, within a bound.
"""
from __future__ import annotations

from typing import Any

#: (specification field, heading), in the order a test writer reads them.
API_FIELDS: tuple[tuple[str, str], ...] = (
    ("api_and_event_contracts", "Endpoints and events"),
    ("data_contracts", "Data shapes"),
    ("error_catalogue", "Errors and the messages they carry"),
    ("interface_design", "The interface a person sees"),
)

#: The most the reference takes; past it, the rest is named as in the document.
MOST_REFERENCE_CHARS = 12_000


def api_reference(specification: Any) -> str:
    """The specification's endpoints, data shapes, errors and interface, as one block; "" when it has none."""
    if specification is None:
        return ""
    blocks = []
    for field, heading in API_FIELDS:
        entries = [str(entry).strip() for entry in getattr(specification, field, None) or [] if str(entry).strip()]
        if entries:
            blocks.append(f"{heading}:\n" + "\n".join(f"- {entry}" for entry in entries))
    if not blocks:
        return ""
    text = "\n\n".join(blocks)
    if len(text) > MOST_REFERENCE_CHARS:
        text = text[:MOST_REFERENCE_CHARS].rsplit("\n", 1)[0] + "\n... (the rest is in /docs/technical_specification.md)"
    return (
        "--- The product's API, as the specification decides it ---\n"
        "Write the tests against these paths, fields, status codes, messages and labels, "
        "word for word; where one is not given here, the specification has it.\n" + text + "\n\n"
    )


__all__ = ["API_FIELDS", "MOST_REFERENCE_CHARS", "api_reference"]
