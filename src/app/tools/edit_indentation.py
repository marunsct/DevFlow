"""An edit matched with a different left margin writes its replacement at the file's margin (LF.1422, plan FX.6).

`edit_artifact` forgives a `find` indented differently from the file: it matches the passage ignoring each line's
indentation (`repository._indentation_insensitive_span`). It then wrote `replace` as sent, at the `find`'s margin and
not the file's. Measured on one medium run's fixer: its `find` and `replace` both carried two spaces more than the
file - the read's gutter copied as indentation - the passage matched, and the replacement, two spaces too deep,
left the file unparseable ("unexpected indent"); the edit was refused at the stage's last calls and the defect stayed
open.

Here the replacement is moved by the same difference: when every non-blank line of the `find` sits the same number
of columns off the line it matched, each non-blank line of `replace` is moved by that many columns. Anything less
certain - lines off by different amounts, tabs against spaces, a replacement line too shallow to move - leaves
`replace` as it was, and the parse check judges it as before. No language is special: a margin is a margin.
"""
from __future__ import annotations


def _margin(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _the_shift(region: str, find: str) -> int | None:
    """Columns the file's lines sit right of the `find`'s (negative: left), the same for every non-blank line; else None."""
    matched = [line for line in region.splitlines() if line.strip()]
    wanted = [line for line in find.splitlines() if line.strip()]
    if not matched or len(matched) != len(wanted):
        return None
    if [line.strip() for line in matched] != [line.strip() for line in wanted]:
        return None
    shifts = set()
    for have, sent in zip(matched, wanted):
        have_margin, sent_margin = _margin(have), _margin(sent)
        if ("\t" in have_margin) != ("\t" in sent_margin) and have_margin and sent_margin:
            return None  # tabs against spaces: a column count says nothing
        shifts.add(len(have_margin) - len(sent_margin))
    return shifts.pop() if len(shifts) == 1 else None


def reindented(region: str, find: str, replace: str) -> str:
    """`replace` moved by the columns `region` (the file's matched text) sits off `find`; `replace` itself when they
    agree, when the lines are off by different amounts, or when a line of `replace` is too shallow to move left."""
    shift = _the_shift(region, find)
    if not shift:
        return replace
    lines = replace.split("\n")
    if shift < 0:
        if any(line.strip() and len(_margin(line)) < -shift for line in lines):
            return replace
        return "\n".join(line[-shift:] if line.strip() else line for line in lines)
    first = next((line for line in region.splitlines() if line.strip()), "")
    unit = "\t" if _margin(first).startswith("\t") else " "
    return "\n".join(unit * shift + line if line.strip() else line for line in lines)


__all__ = ["reindented"]
