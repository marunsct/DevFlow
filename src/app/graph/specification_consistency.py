"""The first draft of a specification checked for values its sections repeat differently, before its first review
(plan PA.7).

Measured: design reaches the escalation on 9 of 11 small runs, and 9 of 11 first drafts go back, mostly for
contradictions between sections written in separate calls - "entry file name inconsistent across the
specification", "advice marked declined but its limit still specified"; a live medium run needed 6 reviews (17
gating findings) before approval. `DESIGN_REVISION_CROSS_CHECKED` checks a revision; the first draft had no pass.

The values sections repeat are compared mechanically (`disagreements`):
- each route's status codes, against what `api_and_event_contracts` and `interface_contract` give it;
- each source file named with its folder, against the file plan, and a file the plan names with another extension;
- the file a start command runs, across the sections that say how the product starts;
- each limit - a number of characters, items, bytes, requests - given for one subject;
- each advice item's decision: decided twice differently, or declined and then cited by another section.

Statements that contradict each other in different words, which no comparison of values finds, are named by one
call first (`specification_meaning`, a draft long enough that its reviewer would not read it whole).

Only when some disagree, one call is shown just those lines and rewrites the ones that must change
(`settled`); every other line is kept as it was, and a call that fails leaves the draft as it was. Always on: it
is a quality fix, and costs no call on a draft with nothing to settle.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: What the run log says whenever the pass acts.
SAID = "Specification consistency pass"
#: Disagreements shown to the one call; lines of one, and characters of a line.
MOST_DISAGREEMENTS = 20
MOST_LINES = 6
LINE_LIMIT = 700

#: The sections that give a route its status codes.
_ROUTE_AUTHORITY = ("api_and_event_contracts", "interface_contract")
#: Sections whose lines are records, not statements: never compared or rewritten here.
_RECORDS = frozenset({"decisions"})


@dataclass
class Disagreement:
    """Lines of the specification that say different things about one subject."""

    kind: str
    subject: str
    why: str
    lines: list[tuple[str, str]] = field(default_factory=list)


def _sections(specification: Any) -> dict[str, list[str]]:
    """Each section as its lines: a list's entries, a text's lines. Records are left out."""
    if isinstance(specification, dict):
        dumped = specification
    else:
        try:
            dumped = specification.model_dump(mode="json")
        except Exception:  # noqa: BLE001 - a plain object: its attributes as they are
            dumped = dict(getattr(specification, "__dict__", {}) or {})
    found: dict[str, list[str]] = {}
    for name, value in dumped.items():
        if name in _RECORDS:
            continue
        if isinstance(value, str):
            lines = [line.strip() for line in value.splitlines() if line.strip()]
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            lines = [" ".join(item.split()) for item in value if item.strip()]
        else:
            continue
        if lines:
            found[name] = lines
    return found


# --- routes and their status codes -----------------------------------------------------------------------------------

_ROUTE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+`?(/[^\s`'\",;)\]]*)")
#: A three-digit status code; "400/422" is two, a path's "/v1/200" none.
_CODE = re.compile(r"(?<![\w.:$#-])(?<![A-Za-z_]/)([1-5]\d\d)(?![\w:%-])(?!\.\d)(?!/[A-Za-z_])")
_SAYS_A_STATUS = re.compile(r"(?:answer|return|respon|send|status|http|->|→|=>|code|with|replies|reply)[^\n]{0,14}$",
                            re.I)
#: What may stand between two codes given together: "400/422", "204 No Content or 404 Not Found".
_CHAINED = re.compile(r"^[\s,/()]*(?:[A-Z][A-Za-z]*\s*){0,3}[\s,/()]*(?:or|and)?[\s,/()]*$")
#: Where a route's clause ends: its sentence.
_CLAUSE_END = re.compile(r"(?<=[A-Za-z0-9)\]])\.\s|\n")
_NOT_A_STATUS = re.compile(r"^\s*(?:characters?|chars?|items?|ms|milliseconds?|seconds?|bytes?|px|words?|lines?|"
                           r"records?|entries|requests?|results?|rows?|times?)\b", re.I)


def _route_key(method: str, path: str) -> str:
    path = path.split("?", 1)[0].rstrip(".:").rstrip("/") or "/"
    path = re.sub(r"\{[^}/]*\}|:[A-Za-z_]\w*|<[^>/]*>", "{}", path)
    return f"{method.upper()} {path}"


def _codes(segment: str) -> set[str]:
    codes: set[str] = set()
    last_end = -1
    for match in _CODE.finditer(segment):
        if not 100 <= int(match.group(1)) <= 599 or _NOT_A_STATUS.match(segment[match.end():]):
            continue
        before = segment[max(0, match.start() - 24):match.start()]
        chained = last_end >= 0 and _CHAINED.match(segment[last_end:match.start()]) is not None
        if _SAYS_A_STATUS.search(before) or chained:
            codes.add(match.group(1))
            last_end = match.end()
    return codes


def _routes_in(statement: str, whole: bool = False) -> dict[str, set[str]]:
    """Each route a statement names, with the status codes it gives it: those after its name in its sentence, or up to
    the next route's name when `whole` (a contract's entry is about its route throughout)."""
    found = list(_ROUTE.finditer(statement))
    routes: dict[str, set[str]] = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(statement)
        segment = statement[match.end():end]
        stop = None if whole else _CLAUSE_END.search(segment)
        segment = segment[:stop.start()] if stop else segment
        routes.setdefault(_route_key(match.group(1), match.group(2)), set()).update(_codes(segment))
    return routes


def _route_disagreements(sections: dict[str, list[str]]) -> list[Disagreement]:
    """A route given a code the contracts do not give it.

    `api_and_event_contracts` lists every answer of a route; `interface_contract` lists only the answers the criteria
    probe, so against it alone only a different success code disagrees (201 against 200), not an error it leaves out.
    """
    given: dict[str, set[str]] = {}
    complete: set[str] = set()
    where: dict[str, list[tuple[str, str]]] = {}
    for name in _ROUTE_AUTHORITY:
        for line in sections.get(name, []):
            for route, codes in _routes_in(line, whole=True).items():
                given.setdefault(route, set()).update(codes)
                if codes:
                    where.setdefault(route, []).append((name, line))
                    if name == "api_and_event_contracts":
                        complete.add(route)
    found: dict[str, Disagreement] = {}
    for name, lines in sections.items():
        if name in _ROUTE_AUTHORITY:
            continue
        for line in lines:
            for route, codes in _routes_in(line).items():
                known = given.get(route, set())
                other = codes - known
                if route not in complete:
                    succeeds = {code for code in known if code.startswith("2")}
                    other = {code for code in other if code.startswith("2") and succeeds}
                if not known or not other:
                    continue
                entry = found.setdefault(route, Disagreement(
                    "status code", route,
                    f"{route} answers {', '.join(sorted(known))} in the contracts", list(where[route][:2])))
                entry.why += f"; `{name}` gives it {', '.join(sorted(other))}"
                entry.lines.append((name, line))
    return list(found.values())


# --- files -----------------------------------------------------------------------------------------------------------

def _suffixes() -> frozenset[str]:
    from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, SCRIPTED_MARKUP_SUFFIXES

    return frozenset(BEHAVIOUR_SUFFIXES | SCRIPTED_MARKUP_SUFFIXES)


def _file_pattern(with_folder: bool) -> re.Pattern[str]:
    suffixes = "|".join(sorted((re.escape(s.lstrip(".")) for s in _suffixes()), key=len, reverse=True))
    folder = r"(?:\./)?(?:[\w.@-]+/)+" if with_folder else ""
    return re.compile(rf"(?<![\w/.:@*-])({folder}[\w-][\w.-]*\.(?:{suffixes}))(?![\w/*-])")


def _plain(path: str) -> str:
    while path.startswith(("./", "../")):
        path = path.split("/", 1)[1]
    return path


def _same_file(one: str, other: str) -> bool:
    one, other = _plain(one), _plain(other)
    return one == other or one.endswith("/" + other) or other.endswith("/" + one)


def _is_a_test(path: str) -> bool:
    from app.analysis.file_kinds import classify_file

    return classify_file(path) == "test"


def _stem(name: str) -> str:
    """A file's name without its last extension: `routes` of `routes.mjs`, `vitest.config` of `vitest.config.ts`."""
    return name.rsplit(".", 1)[0]


def _file_disagreements(sections: dict[str, list[str]], kept: Callable[[str], bool]) -> list[Disagreement]:
    """A source file named with its folder that the file plan does not list, or by a name the plan gives another
    extension. A file the harness keeps, and a test, are no file plan's."""
    from app.graph.drafting import planned_files

    planned = [path for path in planned_files(SimpleNamespace(file_plan=sections.get("file_plan", []))) if path]
    if not planned:
        return []
    names = {path.rsplit("/", 1)[-1] for path in planned}
    stems = {}
    for path in planned:
        base = path.rsplit("/", 1)[-1]
        stems.setdefault(_stem(base), []).append(path)
    with_folder, bare = _file_pattern(True), _file_pattern(False)
    found: dict[str, Disagreement] = {}
    for name, lines in sections.items():
        if name == "file_plan":
            continue
        for line in lines:
            for match in with_folder.finditer(line):
                path = match.group(1)
                if line[max(0, match.start() - 3):match.start()].endswith("//") or _is_a_test(path) or kept(path):
                    continue
                if not any(_same_file(path, other) for other in planned):
                    entry = found.setdefault(path, Disagreement(
                        "file", path, f"`{path}` is named here and is not in the file plan"))
                    entry.lines.append((name, line))
            for match in bare.finditer(line):
                base = match.group(1)
                stem = _stem(base)
                if base in names or stem not in stems or _is_a_test(base) or kept(base):
                    continue
                entry = found.setdefault(base, Disagreement(
                    "file", base, f"`{base}` is named here; the file plan names {', '.join(stems[stem])}"))
                entry.lines.append((name, line))
    return list(found.values())


#: A statement about how the product starts.
_STARTS = re.compile(r"\b(?:start\w*|entry|exec\w*|launch\w*|serve[sd]?|boot\w*)\b", re.I)


def _programs() -> frozenset[str]:
    try:
        from app.tools.sandbox import ROLE_EXECUTABLES

        return frozenset(name for names in ROLE_EXECUTABLES.values() for name in names)
    except Exception:  # noqa: BLE001 - no table, no start commands to compare
        return frozenset()


def _start_disagreements(sections: dict[str, list[str]]) -> list[Disagreement]:
    programs = _programs()
    if not programs:
        return []
    suffixes = "|".join(sorted((re.escape(s.lstrip(".")) for s in _suffixes()), key=len, reverse=True))
    command = re.compile(rf"(?<![\w/.-])([\w.-]+)\s+((?:\./)?(?:[\w.-]+/)*[\w-][\w.-]*\.(?:{suffixes}))(?![\w/-])")
    started: dict[str, list[tuple[str, str, str]]] = {}
    for name, lines in sections.items():
        for line in lines:
            if not _STARTS.search(line):
                continue
            for match in command.finditer(line):
                program, path = match.group(1), match.group(2)
                if program in programs and not _is_a_test(path):
                    started.setdefault(program, []).append((path, name, line))
    found = []
    for program, uses in started.items():
        distinct: list[str] = []
        for path, _, _ in uses:
            if not any(_same_file(path, other) for other in distinct):
                distinct.append(path)
        if len(distinct) > 1 and len({name for _, name, _ in uses}) > 1:
            lines = list(dict.fromkeys((name, line) for _, name, line in uses))
            found.append(Disagreement("start command", program,
                                      f"`{program}` is said to start {' and '.join(f'`{p}`' for p in distinct)}",
                                      lines))
    return found


# --- limits ----------------------------------------------------------------------------------------------------------

_UNIT = (r"(?P<unit>characters?|chars?|items?|bytes?|kb|mb|requests?|entries|entry|tags?|records?|results?|words?|"
         r"lines?|files?|notes?|rows?)")
_LIMIT = re.compile(
    rf"(?P<pre>[^.;:\n]{{0,60}}?)\b(?:at most|up to|no more than|maximum(?: of)?|max(?:imum)?\.?|limit(?:ed)? (?:of|to)"
    rf"|capped at|cap of|not exceed(?:ing)?|(?:between|from)\s+\d+\s+(?:and|to)|\d+\s*(?:-|–|to)(?=\s*\d))\s*"
    rf"(?P<n>\d[\d,]*)\s*{_UNIT}\b",
    re.I,
)
_FILLER = frozenset("""
a an the of is are be must should shall can may will each every any its their per with in on to for and or not no
than more less it this that which field value length long longest size total number count allowed accepts accept
characters character chars items item string strings text input inputs between from only also when if
""".split())


def _subject(before: str) -> str:
    words = [word.lower().strip("'\"`") for word in re.findall(r"[A-Za-z_][\w'`\"-]*", before)]
    for word in reversed(words):
        if len(word) >= 3 and word not in _FILLER:
            return word
    return ""


def _unit(text: str) -> str:
    unit = text.lower()
    unit = {"chars": "characters", "char": "characters", "entry": "entries"}.get(unit, unit)
    return unit[:-1] if unit.endswith("s") and unit not in {"entries", "bytes"} else unit


def _limit_disagreements(sections: dict[str, list[str]]) -> list[Disagreement]:
    seen: dict[tuple[str, str], dict[str, list[tuple[str, str]]]] = {}
    for name, lines in sections.items():
        for line in lines:
            for match in _LIMIT.finditer(line):
                subject = _subject(match.group("pre"))
                if not subject:
                    continue
                number = match.group("n").replace(",", "")
                key = (subject, _unit(match.group("unit")))
                seen.setdefault(key, {}).setdefault(number, []).append((name, line))
    found = []
    for (subject, unit), numbers in seen.items():
        sections_saying = {name for lines in numbers.values() for name, _ in lines}
        if len(numbers) > 1 and len(sections_saying) > 1:
            lines = list(dict.fromkeys(pair for pairs in numbers.values() for pair in pairs))
            found.append(Disagreement("limit", f"{subject} ({unit})",
                                      f"the most {unit}s for {subject}: " + " and ".join(sorted(numbers)), lines))
    return found


# --- advice decisions ------------------------------------------------------------------------------------------------

_DECISION = re.compile(r"^\s*\[?([A-Z]{2,3}-\d+)\]?\s*[:\-–—]\s*\(?(partially adopted|adopted|declined|rejected|deferred)",
                       re.I)
_SAYS_DECLINED = re.compile(r"\b(?:declin\w*|reject\w*|not adopted|deferred|out of scope)\b", re.I)


def _advice_disagreements(sections: dict[str, list[str]], advice: dict[str, list[str]] | None) -> list[Disagreement]:
    decided: dict[str, dict[str, str]] = {}
    for line in sections.get("specialist_advice_decisions", []):
        found = _DECISION.match(line)
        if found:
            verdict = found.group(2).lower().replace("rejected", "declined")
            decided.setdefault(found.group(1).upper(), {}).setdefault(verdict, line)
    disagreements = []
    for ident, verdicts in decided.items():
        if len(verdicts) > 1:
            disagreements.append(Disagreement(
                "advice decision", ident, f"{ident} is decided " + " and ".join(sorted(verdicts)),
                [("specialist_advice_decisions", line) for line in verdicts.values()]))
    texts = _advice_texts(advice)
    for ident, verdicts in decided.items():
        if set(verdicts) != {"declined"}:
            continue
        cited = re.compile(rf"(?<![\w-]){re.escape(ident)}(?!\d)")
        marks = _distinctive_names(texts.get(ident, ""))
        lines = []
        for name, section in sections.items():
            if name == "specialist_advice_decisions":
                continue
            for line in section:
                if _SAYS_DECLINED.search(line):
                    continue
                if cited.search(line) or any(re.search(rf"(?<![\w-]){re.escape(mark)}(?![\w-])", line)
                                             for mark in marks):
                    lines.append((name, line))
        if lines:
            disagreements.append(Disagreement(
                "advice decision", ident, f"{ident} is declined, and another section cites or specifies it",
                [("specialist_advice_decisions", verdicts["declined"]), *lines]))
    return disagreements


def _advice_texts(advice: dict[str, list[str]] | None) -> dict[str, str]:
    if not advice:
        return {}
    try:
        from app.agents.specialist_advice import ADVICE_ROLES, ID_PREFIX
    except Exception:  # noqa: BLE001
        return {}
    return {f"{ID_PREFIX[role]}-{number}": str(item)
            for role in ADVICE_ROLES for number, item in enumerate(advice.get(role) or [], start=1)}


def _distinctive_names(text: str) -> set[str]:
    """The setting and code names an advice item gives: an environment variable, a snake_case or camelCase name."""
    names = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", text))
    names |= set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", text))
    names |= set(re.findall(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b", text))
    return {name for name in names if len(name) >= 6}


# --- the pass --------------------------------------------------------------------------------------------------------

def disagreements(
    specification: Any, advice: dict[str, list[str]] | None = None, kept: Callable[[str], bool] | None = None,
) -> list[Disagreement]:
    """The values the specification's sections repeat differently, found mechanically. Never raises.

    `kept` says whether a path is a file the harness keeps (`app.stacks.contract.owned_by_the_harness`).
    """
    try:
        sections = _sections(specification)
        found = [
            *_route_disagreements(sections), *_file_disagreements(sections, kept or (lambda path: False)),
            *_start_disagreements(sections),
            *_limit_disagreements(sections), *_advice_disagreements(sections, advice),
        ]
    except Exception:  # noqa: BLE001 - nothing found is the draft as it was
        logger.warning("%s: the sections could not be compared", SAID, exc_info=True)
        return []
    for entry in found:
        entry.lines = list(dict.fromkeys(entry.lines))[:MOST_LINES]
    return found[:MOST_DISAGREEMENTS]


def settle_request(found: list[Disagreement], context: str = "") -> str:
    """What the one call is asked: only the lines that disagree, and how to answer."""
    listed = []
    for number, entry in enumerate(found, start=1):
        listed.append(f"{number}. {entry.kind}, {entry.subject}: {entry.why}.")
        listed.extend(f"   - `{section}`: {line[:LINE_LIMIT]}" for section, line in entry.lines)
    return "\n\n".join(part for part in (
        "These lines of a software product's technical specification were written in separate parts and say "
        "different things about the same value or behaviour. For each numbered disagreement, decide which the "
        "specification means - the brief and the API contracts first - and rewrite only the lines that must change "
        "to agree with it. A line that is already right is left out of your reply. An advice item that was "
        "declined is not specified anywhere else; one that is needed is recorded as adopted instead.",
        (context or "").strip()[:20_000],
        "--- The lines that disagree ---\n" + "\n".join(listed),
        'Reply with one JSON object and nothing else: {"lines": [{"section": "<section name>", "old": "<the line '
        'exactly as given above>", "new": "<the line rewritten>"}]}',
    ) if part)


def _rewrites(reply: Any) -> list[dict[str, str]]:
    from app.graph.specification_parts import _the_object_in

    found = _the_object_in(reply) or {}
    return [item for item in found.get("lines") or [] if isinstance(item, dict)]


def _normal(text: str) -> str:
    return " ".join(str(text or "").split())


def settled(
    specification: Any, model: Any, context: str = "", advice: dict[str, list[str]] | None = None,
    kept: Callable[[str], bool] | None = None,
) -> Any:
    """`specification` with the lines that disagree rewritten by one call, every other line as it was.

    `model` may be a function that builds it, called only when something disagrees. Unchanged when nothing
    disagrees, there is no model, or the call fails or answers nothing usable. Never raises.
    """
    found = disagreements(specification, advice, kept)
    if not hasattr(specification, "model_dump"):
        return specification
    from app.graph.specification_meaning import FEWEST_CHARACTERS, contradictions, statements

    long_enough = sum(len(line) for _, line in statements(specification)) >= FEWEST_CHARACTERS
    if not found and not long_enough:
        return specification
    if callable(model) and not hasattr(model, "invoke"):
        model = model()  # built only when there is something to settle or to read
    if model is None:
        return specification
    # Statements that disagree in different words, which no value comparison finds (PA.7, the rest).
    found = [*found, *contradictions(specification, model, context, known=found)]
    if not found:
        return specification
    shown = {(section, _normal(line)) for entry in found for section, line in entry.lines}
    logger.info("%s: %d disagreement(s) between sections: %s", SAID, len(found),
                "; ".join(f"{entry.kind} {entry.subject}" for entry in found))
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.agents.thinking import without_reasoning
        from app.observability.direct_calls import config_for_this_run

        reply = without_reasoning(model).invoke([
            SystemMessage(content="You make the sections of a software technical specification agree."),
            HumanMessage(content=settle_request(found, context)),
        ], **config_for_this_run("principal_architect"))
        rewrites = _rewrites(reply)
    except Exception as error:  # noqa: BLE001 - the draft goes to its review as it was
        logger.info("%s: the disagreements could not be settled: %s", SAID, str(error)[:200])
        return specification
    data = specification.model_dump()
    changed = 0
    for item in rewrites:
        section, old, new = str(item.get("section") or ""), _normal(item.get("old")), _normal(item.get("new"))
        if (section, old) not in shown or not new or new == old:
            continue
        value = data.get(section)
        if isinstance(value, list):
            for index, line in enumerate(value):
                if isinstance(line, str) and _normal(line) == old:
                    value[index] = new
                    changed += 1
        elif isinstance(value, str) and old in _normal(value):
            data[section] = "\n".join(new if _normal(line) == old else line for line in value.splitlines())
            changed += 1
    if not changed:
        logger.info("%s: the call rewrote no line that disagreed", SAID)
        return specification
    try:
        joined = type(specification).model_validate(data)
    except Exception as error:  # noqa: BLE001 - the draft as it was
        logger.info("%s: the settled lines could not be joined: %s", SAID, str(error)[:200])
        return specification
    logger.info("%s: %d line(s) rewritten to agree", SAID, changed)
    return joined


__all__ = ["Disagreement", "SAID", "disagreements", "settle_request", "settled"]
