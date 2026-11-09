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

import re

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


_QUOTED = re.compile(r"""["“'`]([^"”'`\n]{1,80})["”'`]""")


def names_the_specification_changes(brief: str, text: str) -> list[tuple[str, str]]:
    """(the brief's name, the specification's) for each control name the brief quotes that the specification gives only
    in a longer form holding it as a whole word.

    Measured over 30 runs: all four false acceptances came from the brief's wording being overridden on the way to the
    suite - one by a specification that wrote the brief's "All" filter as "All (0)", which the suite then tested.
    """
    from app.analysis.interface_checks import controls_the_brief_names

    quoted = [" ".join(found.split()) for found in _QUOTED.findall(text or "")]
    changed: list[tuple[str, str]] = []
    for name in controls_the_brief_names(brief):
        if name in quoted:
            continue
        word = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")
        longer = next((other for other in quoted if other != name and word.search(other)), None)
        if longer:
            changed.append((name, longer))
    return changed


def api_reference(specification: Any, brief: str = "") -> str:
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
    changed = names_the_specification_changes(brief, text)
    return (
        "--- The product's API, as the specification decides it ---\n"
        "Write the tests against these paths, fields, status codes, messages and labels, "
        "word for word; where one is not given here, the specification has it. Where the brief itself "
        "quotes a name, a label or a form, the brief's words are the ones to use, wherever this list "
        "differs from them.\n" + text + "\n\n"
        + ("Where the brief and this list differ, the brief's words:\n"
           + "\n".join(f'- the brief says "{name}"; the specification has "{longer}": use "{name}"'
                        for name, longer in changed) + "\n\n" if changed else "")
    )


__all__ = ["API_FIELDS", "MOST_REFERENCE_CHARS", "api_reference", "names_the_specification_changes"]
