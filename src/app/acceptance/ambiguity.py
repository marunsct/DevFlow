"""How much of a brief a run would have to guess, read before it starts (plan IN.2).

A thin brief was found at sprint 3: one brief left its page's controls
implicit and scored 5 of 10 against its hidden tests; the medium runs' worst
failures were specification-level choices the brief never made. The preview
counts it first, with no model call: the criteria no line of the brief's
interface section speaks to, and the phrases that ask for a quality without
saying what it is.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*$")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")

#: Words every criterion and interface line shares, which say nothing about which is which.
_COMMON = {
    "every", "each", "with", "that", "this", "when", "from", "have", "than", "into", "their", "there",
    "user", "users", "should", "must", "will", "work", "works", "correctly", "properly", "able",
    "item", "items", "data", "page", "after", "before", "without", "they", "them", "what", "which",
}

#: Phrases that ask for a quality without saying what it is - the guesses a run makes.
VAGUE = re.compile(
    r"\b(?:properly|proper|correctly|appropriate(?:ly)?|as needed|user-friendly|intuitive|modern|robust|"
    r"comprehensive|seamless(?:ly)?|etc\.?|and so on|and more|securely|nice|clean|simple|fast|"
    r"TBD|to be decided)\b",
    re.I,
)


def interface_lines(brief: str) -> list[str]:
    """The lines under a heading that names the interface, the API or the routes."""
    lines, inside = [], False
    for raw in (brief or "").splitlines():
        heading = _HEADING.match(raw)
        if heading:
            inside = bool(re.search(r"\b(interface|api|endpoints?|routes?|commands?|screens?)\b", heading.group(1), re.I))
            continue
        if inside and raw.strip():
            lines.append(raw.strip())
    return lines


def _words(text: str) -> set[str]:
    return {w.lower().rstrip("s") for w in _WORD.findall(text or "")} - {w.rstrip("s") for w in _COMMON}


def criteria_without_an_interface_line(brief: str, criteria: Iterable[Any]) -> list[str]:
    """The ids of criteria no interface line shares a significant word with; every id when there is no interface section."""
    lines = [_words(line) for line in interface_lines(brief)]
    missing = []
    for criterion in criteria:
        words = _words(getattr(criterion, "text", "") or "")
        if not lines or not any(words & line for line in lines):
            missing.append(str(getattr(criterion, "id", "")))
    return missing


def vague_phrases(brief: str) -> list[str]:
    """Each vague phrase the brief uses, once, in the order it first appears."""
    return list(dict.fromkeys(match.group(0).lower() for match in VAGUE.finditer(brief or "")))


__all__ = ["criteria_without_an_interface_line", "interface_lines", "vague_phrases"]
