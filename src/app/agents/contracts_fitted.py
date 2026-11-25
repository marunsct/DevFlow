"""The specification's contracts fitted to a request by entry, never cut mid-word (LF.1470).

The technical lead's request quotes the specification's contract sections for its work orders to copy from. Past the
document budget they were cut blind: the first 60% and the last 40% kept, the middle replaced by a marker. Measured on
one medium run: "... Implements JWT encode/decode usin" then "--- TRUNCATED (23428 chars removed for context limits)
---" then "(401, "Not authenticated"). 2. Extract JWT token ..." - the file plan and function contracts of the files
in the middle gone, mid-word, with no line range to read them from; 40 requests of another run carried the marker.

So the entries are fitted whole: those the selected sprint's own words do not bear on are left out first, and each
section that lost any names the lines of the specification document that hold it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_WORD = re.compile(r"[a-z][a-z0-9_]{3,}")
_A_CRITERION = re.compile(r"\b[A-Z]{1,4}-\d+\b")
_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


def the_sprint_s_words(sprint_plan_text: str, goal: str) -> tuple[set[str], set[str]]:
    """The words of the selected sprint's own entry in the plan, and those only its out-of-scope list uses."""
    inside, outside = str(goal or ""), ""
    try:
        plan = json.loads(sprint_plan_text)
        for sprint in plan.get("sprints") or []:
            if isinstance(sprint, dict) and str(sprint.get("goal") or "").strip() == str(goal or "").strip():
                outside = json.dumps(sprint.get("out_of_scope") or [])
                inside = json.dumps({k: v for k, v in sprint.items() if k != "out_of_scope"})
                break
    except (ValueError, TypeError, AttributeError):
        pass
    words = set(_WORD.findall(inside.lower())) | set(_A_CRITERION.findall(inside))
    return words, set(_WORD.findall(outside.lower())) - words


def line_ranges(document: str) -> dict[str, tuple[int, int]]:
    """Each heading of `document`, lower-cased, with the lines its section spans (1-based, inclusive)."""
    lines = str(document or "").splitlines()
    starts = [(i, len(m.group(1)), m.group(2).strip().lower()) for i, line in enumerate(lines)
              if (m := _HEADING.match(line))]
    found: dict[str, tuple[int, int]] = {}
    for n, (start, level, name) in enumerate(starts):
        end = next((s for s, lv, _ in starts[n + 1:] if lv <= level), len(lines))
        found.setdefault(name, (start + 1, end))
    return found


def fitted(sections: list[tuple[str, list[str]]], budget: int, words: set[str], outside: set[str],
           document: str = "", where: str = "/docs/technical_specification.md") -> str:
    """`sections` ((heading, entries)) as `- entry` lists within `budget`: whole when they fit; past it, the entries
    the sprint's `words` bear on least left out first (those only `outside` words name before any), never one cut,
    and each section that lost any said so with its lines in `where` (from `document`)."""
    def render(kept: list[list[bool]]) -> str:
        ranges = line_ranges(document)
        blocks = []
        for (heading, entries), keep in zip(sections, kept):
            shown = [f"- {entry}" for entry, k in zip(entries, keep) if k]
            gone = len(entries) - len(shown)
            span = ranges.get(heading.lower())
            at = f"lines {span[0]}-{span[1]} of {where}" if span else where
            if gone and not shown:
                blocks.append(f"{heading}: its {gone} entries are for parts this sprint does not build - read "
                              f"{at} when a work order needs one.")
                continue
            block = f"{heading}:\n" + "\n".join(shown)
            if gone:
                block += (f"\n({gone} more entries, for parts this sprint does not build, are left out here: "
                          f"{at}.)")
            blocks.append(block)
        return "\n\n".join(blocks)

    kept = [[True] * len(entries) for _, entries in sections]
    text = render(kept)
    if len(text) <= budget:
        return text

    def score(entry: str) -> tuple[float, int]:
        # The share of its words the sprint uses, less those only its out-of-scope list does: a short entry the
        # sprint names outweighs a long one that mentions it in passing, and leaving out the long one frees more.
        own = set(_WORD.findall(entry.lower())) | set(_A_CRITERION.findall(entry))
        return ((len(own & words) - len(own & outside)) / max(1, len(own)), -len(entry))

    order = sorted(((score(entry), s, e) for s, (_, entries) in enumerate(sections)
                    for e, entry in enumerate(entries)), key=lambda x: x[0])
    for _, s, e in order:
        kept[s][e] = False
        text = render(kept)
        if len(text) <= budget:
            break
    return text


def the_specification_document(repository_root: str | Path | None) -> str:
    """The specification document's text, for its line ranges; "" when there is none."""
    if not repository_root:
        return ""
    try:
        return (Path(repository_root) / "docs" / "technical_specification.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


__all__ = ["fitted", "line_ranges", "the_sprint_s_words", "the_specification_document"]
