"""One entry per item, for a list field a model filled with a formatted list.

A schema asks for `list[str]`. A local model sometimes answers with one string
that holds the whole list - "- first\\n- second\\n- third" - or with entries that
carry their own bullet. Both are valid to the schema and wrong to everything
that reads the field: the document renders "- - first", and a check that walks
the list one entry at a time sees one entry.

Measured on one run. The intake's first success measure was four bulleted
lines in one string, so the sprint plan's coverage checklist numbered four
measures as one, the plan was handed back for "measure 1", and the intake's
own cross-check wrote the capabilities of the first line onto the fourth.
"""

from __future__ import annotations

import re
from typing import Any

#: A list marker at the start of a line: a bullet, or a number with "." or ")".
_A_MARKER = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+")


def one_item_each(items: Any) -> Any:
    """`items` with every formatted list inside an entry split into entries.

    An entry is split only when it has two lines or more and every one of them
    opens with a list marker - prose that happens to contain a line break is
    left whole. A marker on an entry of its own is removed either way. Anything
    that is not a list of strings is returned untouched, for the schema to
    judge.
    """
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        return items
    out: list[str] = []
    for item in items:
        lines = [line for line in item.splitlines() if line.strip()]
        if len(lines) >= 2 and all(_A_MARKER.match(line) for line in lines):
            out.extend(_A_MARKER.sub("", line).strip() for line in lines)
        elif len(lines) == 1 and _A_MARKER.match(lines[0]):
            out.append(_A_MARKER.sub("", lines[0]).strip())
        else:
            out.append(item)
    return [item for item in out if item.strip()] if len(out) != len(items) else out


__all__ = ["one_item_each"]
