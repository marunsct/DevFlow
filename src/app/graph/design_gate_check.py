"""The harness's own check of a design finding that says something is missing from the specification (LF.1504).

Measured on a medium run: after six revisions the run waited for a person on one open gating finding, which said the
specification had no `error_catalogue` section. The current specification had an "Error Catalogue" section of eleven
entries, and the re-review said the finding was resolved - "## Error Catalogue section added at line 210, listing
DUPLICATE_EMAIL (409), ..." - but in its own words, not six consecutive words of the specification, so the quote rule
(LF.1440) refused it. A correct resolution was refused and the gate held on a finding the specification answered.

So where a finding says a section, a key, a field or a route is missing, the harness looks for it in the current
specification itself, and where it is now there, the finding is answered with the harness's own quote: the first line
of that section, or the line that names the term. The check is narrow on purpose:

- only what a "does not exist" phrase is about is what is missing: "there is no `X` key", "the X section ... does not
  exist", "`X` is missing". A section named beside it as a reference ("is missing (component_boundaries line 9)") or
  as where something is ("in the domain model") is not the thing missing;
- a finding that says something is stated wrongly (wrong, contradicts, conflicts, malformed, ...) is not checked: what
  is there has to be read, and only the reviewer's quote answers it;
- a term (a name in backticks or a route) counts only when it was absent from the specification the finding was
  raised on and is present now: a term found anywhere at raise time means the finding was about where it is, which a
  search cannot settle. A section is checked without that: a section that exists answers "it does not exist".
"""
from __future__ import annotations

import json
import re
from typing import Any

#: The words just before a name that say it does not exist: "there is no `X`", "lacks an X section", "no such X".
_SAID_TO_BE_MISSING = re.compile(
    r"\b(?:there (?:is|are) no|(?:has|have) no|no such|lacks?|missing|without|no)\s+(?:(?:an?|the|any)\s+)?`?$", re.I)
#: The words just after a name that say it does not exist: "`X` is missing", "the X section is '_Not specified._'",
#: "the X section referenced by ... does not exist". Words come between only after the noun "section" (or "key", ...),
#: at most ten and within one clause and outside a quote: in "the X specifies 'a body is missing'" X is the subject of
#: another verb, not the thing missing.
_SAID_NOT_TO_EXIST = re.compile(
    r"^`?(?:\s+(?:section|key|field|heading|route|endpoint)(?:\s+[^\s.;:'\"]+){0,10}?)?\s+"
    r"(?:(?:does not|doesn't|do not|don't) exist\b|(?:is|are) (?:missing|absent|empty|not present|not defined|undefined"
    r"|not specified)\b|(?:is|are) ['\"]?_not specified\._)", re.I)
#: A sentence that says something is stated wrongly: what is there must be read, not searched for.
_STATED_WRONGLY = re.compile(
    r"\b(?:wrong|incorrect(?:ly)?|contradict\w*|conflicts?|conflicting|inconsisten\w*|mismatch\w*|malformed|truncated"
    r"|invalid|instead of|rather than)\b", re.I)
#: The words just before a section that make it the place something is, not the thing missing.
_A_PLACE = re.compile(r"\b(?:in|into|to|within|under|from|inside|of|on|at)\s+(?:the\s+|its\s+|an?\s+)?`?$", re.I)
_BACKTICKED = re.compile(r"`([^`\n]{2,80})`")
_A_ROUTE = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[\w/{}\-.:]*")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_REMEDIATION = re.compile(r"\bRequired remediation:", re.I)
#: How much of a quoted line the decision log keeps.
_QUOTE_CHARACTERS = 300


def _sections_of_the_schema() -> tuple[tuple[str, str], ...]:
    from app.agents.specification_document import _SECTIONS

    return _SECTIONS


def _lines(value: Any) -> list[str]:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, dict):
        return [line for item in value.values() for line in _lines(item)]
    if isinstance(value, (list, tuple)):
        return [line for item in value for line in _lines(item)]
    return [] if value is None else [str(value)]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def sections(specification: Any) -> dict[str, list[str]]:
    """The specification's sections by key (the schema's field names), each as its non-empty lines.

    Read from the structured specification (a model or a dict, or its JSON) or from the rendered Markdown document,
    whose headings are mapped back to the fields they render.
    """
    if hasattr(specification, "model_dump"):
        specification = specification.model_dump()
    if isinstance(specification, str) and specification.lstrip().startswith("{"):
        try:
            specification = json.loads(specification)
        except ValueError:
            pass
    if isinstance(specification, dict):
        return {_key(name): _lines(value) for name, value in specification.items()}
    if not isinstance(specification, str):
        return {}
    by_heading = {heading.lower(): field for field, heading in _sections_of_the_schema()}
    found: dict[str, list[str]] = {}
    current = ""
    for raw in specification.splitlines():
        heading = _HEADING.match(raw.strip())
        if heading and len(heading.group(1)) <= 2:
            title = heading.group(2).strip()
            current = by_heading.get(title.lower(), _key(title))
            found.setdefault(current, [])
            continue
        line = raw.strip()
        if line and current:
            found[current].append(line)
    return found


def _known_sections(found: dict[str, list[str]]) -> dict[str, str]:
    """Each section key with the heading a reader names it by."""
    named = {field: heading for field, heading in _sections_of_the_schema()}
    return {key: named.get(key, key.replace("_", " ").title()) for key in {*named, *found}}


def _a_section_pattern(key: str, heading: str) -> re.Pattern[str]:
    spellings = {tuple(key.split("_")), tuple(_key(heading).split("_"))}
    alternatives = []
    for words in spellings:
        joined = r"[\s_-]+".join(map(re.escape, words))
        # One word alone is a section only when called one: "the testing section", not "testing".
        alternatives.append(joined if len(words) > 1 else joined + r"(?=`?\s+(?:section|key|field|heading)\b)")
    return re.compile(r"(?<![\w])(?:" + "|".join(alternatives) + r")(?![\w])", re.I)


def _sentences(text: str) -> list[str]:
    description = _REMEDIATION.split(str(text or ""), maxsplit=1)[0]
    return [part for part in re.split(r"(?<=[.!?])\s+", description) if part.strip()]


def _what_is_missing(text: str, found: dict[str, list[str]]) -> tuple[list[str], list[tuple[str, str]]]:
    """What the finding says does not exist: the sections, and the terms with the section to find each in ("")."""
    known = _known_sections(found)
    patterns = {key: _a_section_pattern(key, heading) for key, heading in known.items()}
    missing_sections: list[str] = []
    terms: list[tuple[str, str]] = []
    def said_to_be_missing(sentence: str, start: int, end: int) -> bool:
        return bool(_SAID_TO_BE_MISSING.search(sentence[:start]) or _SAID_NOT_TO_EXIST.search(sentence[end:]))

    for sentence in _sentences(text):
        places: list[str] = []
        named_sections: set[str] = set()
        for key, pattern in patterns.items():
            for match in pattern.finditer(sentence):
                named_sections.add(match.group(0).lower())
                if _A_PLACE.search(sentence[:match.start()]):
                    places.append(key)
                elif said_to_be_missing(sentence, match.start(), match.end()) and key not in missing_sections:
                    missing_sections.append(key)
        candidates = [(match.group(1).strip(), match.start(1), match.end(1)) for match in _BACKTICKED.finditer(sentence)]
        candidates += [(match.group(0), match.start(), match.end()) for match in _A_ROUTE.finditer(sentence)]
        for name, start, end in candidates:
            if name.lower() in named_sections or _key(name) in known or not said_to_be_missing(sentence, start, end):
                continue
            term = (name, places[0] if places else "")
            if term not in terms:
                terms.append(term)
    return missing_sections, terms


def _says_nothing(line: str) -> bool:
    """A line an empty section is rendered with, or one that says there is nothing."""
    from app.doc_templates.render import NOT_SPECIFIED

    return line.strip() == NOT_SPECIFIED or line.lstrip("-* ").strip().rstrip(".").lower() in {"none", "n/a", ""}


def _a_line_naming(term: str, lines: list[str]) -> str:
    pattern = re.compile(r"(?<![\w])" + r"\s+".join(map(re.escape, term.split())) + r"(?![\w])", re.I)
    return next((line for line in lines if pattern.search(line)), "")


def _where_to_look(found: dict[str, list[str]], place: str) -> list[str]:
    return found.get(place, []) if place else [line for lines in found.values() for line in lines]


def absent_terms(text: str, specification: Any) -> list[str]:
    """The terms a finding says are missing that the specification it was raised on does not name: kept with the
    finding, so a later specification that names them answers it."""
    found = sections(specification)
    if not found:
        return []
    _, terms = _what_is_missing(text, found)
    return [term for term, place in terms if not _a_line_naming(term, _where_to_look(found, place))]


def answered_by_the_specification(text: str, specification: Any, absent_then: list[str] | None = None) -> str:
    """The specification's own words that answer a finding saying something is missing; "" when it does not, or when
    the finding is not one a search can settle (it says something is stated wrongly, or names nothing it can find).

    `absent_then` are the terms the specification the finding was raised on did not name (`absent_terms`).
    """
    if _STATED_WRONGLY.search(str(text or "")):
        return ""
    found = sections(specification)
    missing_sections, terms = _what_is_missing(text, found)
    if not missing_sections and not terms:
        return ""
    headings = _known_sections(found)
    quotes: list[str] = []
    for key in missing_sections:
        lines = [line for line in found.get(key, []) if not line.startswith("#") and not _says_nothing(line)]
        if not lines:
            return ""
        quotes.append(f"{headings[key]}: {lines[0].lstrip('-* ').strip()}")
    for term, place in terms:
        if term not in set(absent_then or []):
            return ""
        line = _a_line_naming(term, _where_to_look(found, place))
        if not line:
            return ""
        quotes.append(line.lstrip("-* ").strip())
    return "; ".join(quote[:_QUOTE_CHARACTERS] for quote in quotes)


__all__ = ["absent_terms", "answered_by_the_specification", "sections"]
