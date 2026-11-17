"""A specification revised in place is kept consistent with the sections left unchanged (LR.42 part 1, D1+D2, behind
`DESIGN_REVISION_CROSS_CHECKED`).

Measured on 5 of 7 language-sweep runs, and on every run of two families before them: the design review named a few
sections, only those were rewritten (`specification_parts.revised_in_place`), and the second review found a rewritten
section contradicting one left as it was - "Graceful shutdown supported" in `deployment` against "No graceful shutdown"
in `function_contracts` - so the design went to the escalation, which settled it in one ruling.

Two cheap steps, no model call of their own unless a disagreement is found:

1. Each revising call is shown what the sections left unchanged say on the subjects its sections and the required
   changes speak of (`related_statements`): shared file paths, names, settings and two-word feature phrases. Picked
   by matching, not by a model, and bounded in size.
2. After the revision, statements the rewritten sections added and statements of the unchanged ones that say opposite
   things about one subject - one says "no X" or "X is not supported", the other states X - are found by matching
   (`opposite_statements`). If any are, one bounded call rewrites the unchanged sections holding them (at most
   `SECTIONS_PER_REVISION`), shown the pairs; a call that fails leaves the revision as it was.

A quality change for the design stage, but a new model-facing step whose cost is not yet measured, so a switch.
"""
from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words it puts in a revising request whenever it acts, which the audit's switch-firing check reads.
SAID = "Cross-checked against the sections left unchanged"

#: Characters of unchanged statements shown to one revising call, and of one statement.
RELATED_BUDGET = 6_000
STATEMENT_LIMIT = 600
#: Statement pairs named in the call that brings unchanged sections into line.
MOST_PAIRS = 12


def enabled() -> bool:
    return is_on("DESIGN_REVISION_CROSS_CHECKED", ON_BY_DEFAULT)


# --- subjects -------------------------------------------------------------------------------------------------------

_IDENTIFIERS = (
    re.compile(r"`([^`\n]{3,80})`"),                                   # anything quoted as code
    re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+)"),                  # a path with a folder
    re.compile(r"\b([A-Za-z_][\w-]*\.[A-Za-z][A-Za-z0-9]{0,4})\b"),    # a file name with an extension
    re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b"),                # an environment variable
    re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"),                # a snake_case name
    re.compile(r"\b([a-z]+[A-Z][A-Za-z0-9]*)\b"),                      # a camelCase name
    re.compile(r"\b([A-Za-z_]\w{2,})\("),                              # a call
)
_NOT_A_NAME = frozenset({"e.g", "i.e", "etc", "and/or", "n/a"})

_WORD = re.compile(r"[A-Za-z][A-Za-z-]*")
#: Words that never make a subject: grammar, and what reviews and specifications say of themselves.
_COMMON = frozenset("""
about above after again against also always another anything because been before being below between both cannot
does doing done down during each either else every from further have having here into itself just keep kept less
many more most much must need needs neither none only other otherwise over same should shall since some such than
that their them then there these they this those through under until upon very want were what when where whether
which while will with within without would your yours make makes made like line lines says said state states stated
claims claim contradicts contradiction contradictory inconsistent inconsistency conflicts conflict blocking major
minor finding findings change changes changed required requires require missing section sections specification spec
review reviewer listed lists list given gives give uses used using names named name describes described defines
defined mention mentions mentioned already still instead whereas however although though even well exactly
""".split())


def _words(text: str) -> list[str]:
    return [word.lower().strip("-") for word in _WORD.findall(text or "")]


def phrases(text: str, *, section_names: Iterable[str] = ()) -> set[str]:
    """The two-word feature phrases of `text`: two words in a row, neither common, each of four letters or more."""
    words = _words(text)
    own = {name.replace("_", " ") for name in section_names}
    found = set()
    for first, second in zip(words, words[1:]):
        if len(first) >= 4 and len(second) >= 4 and first not in _COMMON and second not in _COMMON:
            phrase = f"{first} {second}"
            if phrase not in own:
                found.add(phrase)
    return found


def identifiers(text: str) -> set[str]:
    """The paths, file names, settings and code names `text` mentions."""
    found = set()
    for pattern in _IDENTIFIERS:
        for match in pattern.finditer(text or ""):
            term = match.group(1).strip().rstrip(".,:;")
            if len(term) >= 4 and term.lower() not in _NOT_A_NAME:
                found.add(term)
    return found


def _pattern_of(subject: str) -> str:
    if " " in subject:  # a phrase: any case, a hyphen for the space
        first, second = subject.split(" ", 1)
        return rf"(?i:\b{re.escape(first)}[\s-]+{re.escape(second)}\b)"
    return rf"(?<![\w-]){re.escape(subject)}(?![\w-])"


@functools.lru_cache(maxsize=4096)
def _mentioning(subject: str) -> re.Pattern[str]:
    return re.compile(_pattern_of(subject))


def mentions(statement: str, subject: str) -> bool:
    return _mentioning(subject).search(statement or "") is not None


# --- statements -----------------------------------------------------------------------------------------------------

def statements(value: Any) -> list[str]:
    """A section's value as its statements: one per list entry, line of text or field of a record."""
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, dict):
        return [f"{key}: {item if isinstance(item, str) else json.dumps(item, default=str)}" for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        found: list[str] = []
        for item in value:
            if isinstance(item, str):
                found.extend(statements(item))
            else:
                found.append(json.dumps(item, default=str))
        return found
    return [str(value)]


def _dumped(specification: Any) -> dict[str, Any]:
    try:
        return specification.model_dump(mode="json")
    except Exception:  # noqa: BLE001 - a plain object: its attributes as they are
        return dict(getattr(specification, "__dict__", {}) or {})


def related_statements(
    specification: Any, names: Iterable[str], left_out: Iterable[str], required_changes: str,
    *, budget: int = RELATED_BUDGET,
) -> dict[str, list[str]]:
    """What the sections not being rewritten, and not shown already, say on the subjects of `names` and the changes.

    Subjects are the names and two-word phrases of the required changes, and the names in the sections being
    rewritten. A statement is ranked by the rarer subjects it shares, those of the changes counting double, and the
    best are kept within `budget` characters.
    """
    dumped = _dumped(specification)
    names = list(names)
    skipped = set(names) | set(left_out)
    changes = required_changes or ""
    own_text = "\n".join(statements([dumped.get(name) for name in names]))
    weight = {term: 2.0 for term in identifiers(changes) | phrases(changes, section_names=dumped)}
    for term in identifiers(own_text):
        weight.setdefault(term, 1.0)
    if not weight:
        return {}
    matched = []
    for name, value in dumped.items():
        if name in skipped:
            continue
        for statement in statements(value):
            terms = [term for term in weight if mentions(statement, term)]
            if terms:
                matched.append((name, statement, terms))
    if not matched:
        return {}
    spread = {term: sum(term in terms for _, _, terms in matched) for term in weight}
    ranked = sorted(
        enumerate(matched),
        key=lambda item: (-sum(weight[t] / spread[t] for t in item[1][2]), item[0]),
    )
    kept: dict[str, list[str]] = {}
    used = 0
    for _, (name, statement, _) in ranked:
        statement = statement[:STATEMENT_LIMIT]
        if used + len(statement) > budget:
            continue
        kept.setdefault(name, []).append(statement)
        used += len(statement)
    # In the specification's own order, section by section.
    return {name: kept[name] for name in dumped if name in kept}


def related_block(specification: Any, names: Iterable[str], left_out: Iterable[str], required_changes: str) -> str:
    """The part of a revising request that shows the related unchanged statements, or '' with none."""
    names = list(names)
    related = related_statements(specification, names, left_out, required_changes)
    if not related:
        return ""
    logger.info("%s: %s shown to the revision of %s", SAID, ", ".join(related), ", ".join(names))
    return (
        f"--- {SAID}: what they say on the same subjects ---\n" + json.dumps(related, indent=1)
        + "\nThose sections are not rewritten now. Keep every path, name, setting and claim in the sections you "
        "rewrite consistent with these statements; where a required change makes one of them untrue, follow the "
        "required change."
    )


# --- opposite statements --------------------------------------------------------------------------------------------

_NEGATOR = (r"(?:no|not|never|without|cannot|can't|doesn't|don't|isn't|aren't|won't|nor|excludes?|excluded|"
            r"out\s+of\s+scope:?)")
_BETWEEN = (r"(?:(?:support|implement|handle|provide|use|read|need|require|include|offer|perform|expose|log|emit|"
            r"apply|enable|accept|do|does|is|are|be)(?:s|d|ed|es)?|any|a|an|the)")
_DENIED_AFTER = (r"(?:is|are|was|will\s+be)?\s*(?:not\s+(?:supported|implemented|handled|provided|used|read|needed|"
                 r"required|included|performed|available|exposed|enabled|applied|done)|unsupported|disabled|omitted|"
                 r"out\s+of\s+scope|deferred)\b")


@functools.lru_cache(maxsize=4096)
def _denying(subject: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    pattern = _pattern_of(subject)
    return (re.compile(rf"(?i:\b{_NEGATOR}(?:\s+{_BETWEEN}){{0,2}})\s+{pattern}"),
            re.compile(rf"{pattern}(?i:[\s:,-]+{_DENIED_AFTER})"))


def denies(statement: str, subject: str) -> bool:
    """Whether `statement` says `subject` is not there: "no X", "does not support X", "X is not supported"."""
    before, after = _denying(subject)
    return bool(before.search(statement or "") or after.search(statement or ""))


def opposite_statements(
    rewritten: dict[str, list[str]], unchanged: dict[str, list[str]],
) -> list[tuple[str, str, str, str, str]]:
    """(subject, rewritten section, its statement, unchanged section, its statement) for each pair saying opposite things.

    Subjects are the names and two-word phrases both statements mention; one statement denies the subject, the other
    mentions it without denying it.
    """
    sections = [*rewritten, *unchanged]
    pairs: list[tuple[str, str, str, str, str]] = []
    for section, said in rewritten.items():
        for statement in said:
            subjects = sorted(identifiers(statement) | phrases(statement, section_names=sections))
            denied = {subject for subject in subjects if denies(statement, subject)}
            for other, theirs in unchanged.items():
                for their in theirs:
                    for subject in subjects:
                        if mentions(their, subject) and (subject in denied) != denies(their, subject):
                            pairs.append((subject, section, statement, other, their))
                            break
    return pairs


def _added(before: Any, after: Any) -> list[str]:
    old = set(statements(before))
    return [statement for statement in statements(after) if statement not in old]


def _rewritten_statements(previous: Any, revised: Any, chosen: list[str]) -> dict[str, list[str]]:
    """The statements the revision added, by section."""
    before, after = _dumped(previous), _dumped(revised)
    found = {name: _added(before.get(name), after.get(name)) for name in chosen}
    return {name: added for name, added in found.items() if added}


def brought_into_line(
    previous: Any, revised: Any, chosen: Iterable[str], required_changes: str, model: Any, context: str,
) -> Any:
    """`revised` with the unchanged sections that now contradict a rewritten one rewritten to agree; else `revised`.

    Only statements the revision added are checked, so a disagreement it did not make is left to the review.
    """
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.graph.specification_parts import SECTIONS_PER_REVISION, _sections_as_json, _the_form_of, revision_reply

    chosen = list(chosen)
    after = _dumped(revised)
    unchanged = {name: statements(value) for name, value in after.items() if name not in chosen}
    pairs = opposite_statements(_rewritten_statements(previous, revised, chosen), unchanged)
    if not pairs:
        return revised
    counts: dict[str, int] = {}
    for pair in pairs:
        counts[pair[3]] = counts.get(pair[3], 0) + 1
    order = list(after)
    names = tuple(sorted(counts, key=lambda name: (-counts[name], order.index(name)))[:SECTIONS_PER_REVISION])
    listed = "\n".join(
        f"- on \"{subject}\": `{section}` now says: {statement[:STATEMENT_LIMIT]}\n"
        f"  `{other}` still says: {their[:STATEMENT_LIMIT]}"
        for subject, section, statement, other, their in [pair for pair in pairs if pair[3] in names][:MOST_PAIRS]
    )
    parameters = convert_to_openai_tool(type(revised))["function"]["parameters"]
    current = _sections_as_json(revised, names)
    request = "\n\n".join(part for part in (
        "A software product's technical specification was revised: only the sections the review named were "
        "rewritten, and statements in them now disagree with sections left as they were. Rewrite the sections "
        "below so they agree with the rewritten ones and the required changes, and change nothing else in them.",
        (context or "").strip(),
        "--- Required changes ---\n" + (required_changes or "").strip()[:20_000],
        f"--- {SAID}: statements that now disagree ---\n{listed}",
        _the_form_of(parameters, names),
        "--- The sections to rewrite, as they stand ---\n" + json.dumps(current, indent=1, default=str),
        "Reply with one JSON object and nothing else. Its keys are exactly: " + ", ".join(names)
        + ". Each value has the form its schema gives, whatever the section holds now.",
    ) if part)
    written = revision_reply(model, request, names, parameters, current)
    if written is None:
        logger.info("%s: %s disagree with the revision and could not be brought into line", SAID, ", ".join(names))
        return revised
    try:
        joined = type(revised).model_validate({**revised.model_dump(), **written})
    except Exception as error:  # noqa: BLE001 - the revision stands as it was
        logger.info("%s: the sections brought into line could not be joined: %s", SAID, str(error)[:300])
        return revised
    logger.info("%s: %s brought into line with the revision (%d statements disagreed)", SAID, ", ".join(names),
                len(pairs))
    return joined


__all__ = [
    "ON_BY_DEFAULT", "SAID", "brought_into_line", "denies", "enabled", "identifiers", "opposite_statements",
    "phrases", "related_block", "related_statements", "statements",
]
