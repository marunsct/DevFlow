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


#: Between a denying word and what it denies of the product: "does not support any X". Not a copula ("must not be the
#: empty string" is a rule on a value) and not an act done to something the product has ("does not log X").
_BETWEEN_A_DENIAL = (r"(?:(?:support|implement|handle|provide|use|need|require|include|offer|perform|apply|enable|accept)"
                     r"(?:s|d|ed|es)?|any|a|an|the)")


@functools.lru_cache(maxsize=4096)
def _denying(subject: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    pattern = _pattern_of(subject)
    return (re.compile(rf"(?i:\b{_NEGATOR}(?:\s+{_BETWEEN_A_DENIAL}){{0,2}})\s+{pattern}"),
            re.compile(rf"{pattern}(?i:[\s:,-]+{_DENIED_AFTER})"))


#: After "no X": what is done to X or what happens, not whether the product has X - "No request body is logged",
#: "No database access occurs", "No other table exists". Words that say the product has no X stay a denial ("No
#: external dependencies are required").
_AN_ACT_ON_IT = re.compile(
    r"(?i)^[^,;:]*?\b(?:(?:is|are|was|were|gets?|being)\s+(?:ever\s+|never\s+|not\s+)?(?!(?:required|needed|used|"
    r"supported|implemented|provided|available|included|offered|added|shipped|planned|built|installed|configured|"
    r"bundled|present|allowed|enabled|exposed)\b)(?:\w+ed|written|sent|shown|kept|given|taken|done|seen|read|"
    r"thrown|returned)|occurs?|happens?|exists?|takes\s+place|here|in\s+this\s+(?:file|module|class|component|layer))\b")
#: A list's first item opening with one of these is a rule on a value or an act on something the product has, not a
#: list of what it leaves out: "must not be null, empty string ...", "does not log request bodies, titles ...".
_NOT_A_LIST_OF_PARTS = frozenset("""
be is are was were been log logs emit emits read reads write writes store stores persist persists return returns
print prints send sends show shows expose exposes leak leaks contain contains change changes modify modifies
""".split())


# A denial is about the product only when it is said of the product, not of one case of it (LF.1633). Measured over the
# 147 design escalations of 143 stored runs: 989 pairs found by the plain "no X" against "X", and none of the hundreds
# read in full was a contradiction that mattered - "returns 204 with no response body" against "the response body is an
# array", "if no note exists" against "the note exists", "without I/O side effects" against "without side effects", a
# decision's rejected alternative ("No graceful shutdown") against the decision it led to. With the rules below: 99.
_CLAUSES = re.compile(r"(?<=[.;!?])\s+|\n+|\s+[\u2014\u2013]\s+|\s+--?\s+")
_WORDS = re.compile(r"[\w'/{}<>-]+|[()]")
#: Words that make what follows one case of the product: a condition, a route's or a call's outcome, a test's step.
_A_CASE = frozenset("""
if when whenever unless where while once after before until upon during on for with given returns return returned
responds respond answers answer gives sends send then else otherwise ensure ensures assert asserts verify verifies
expect expects check checks test tests even only except
""".split())
#: Words opening a clause that lists what the product leaves out.
_LEFT_OUT = re.compile(
    r"(?i)^\W*(?:[\w-]+\s+){0,3}?(?:deferred|defers?|out\s+of\s+scope|not\s+in\s+scope|excluded|excludes?|"
    r"explicitly\s+excluded|non-goals?|not\s+included|left\s+out|declined|rejected)\b")
#: Words anywhere in a clause that keep it from stating its subject as part of the product: a denial, a deferral, an
#: option, a hypothesis.
_NOT_A_STATEMENT_OF_IT = re.compile(
    r"(?i)\b(?:no|not|never|without|cannot|nor|neither|none|zero|lack(?:s|ing)?|absent|absence|n't|"
    r"defer(?:s|red)?|exclud(?:e|es|ed|ing)|out\s+of\s+scope|reject(?:s|ed)?|declined?|avoid(?:s|ed)?|"
    r"instead\s+of|rather\s+than|beyond|disabled?|omit(?:s|ted)?|unsupported|unused|would|could|might|optional(?:ly)?|"
    r"alternatives?)\b")
#: Words that may stand between a denying word and the subject it denies: "does not support any X".
_MOST_WORDS_BETWEEN = 3
#: Words a clause may say before its denying word and still deny of the product: "The service does not ...".
_MOST_WORDS_BEFORE = 6
#: Fields of a decision record that are not what was decided: the options turned down, the reasons and the evidence.
DECIDED_FIELDS = ("title", "decision")


def claims(value: Any) -> list[str]:
    """A section's value as the statements it makes of the product: as `statements`, but a decision record is its
    title and its decision, not the alternatives it turned down or the context it weighed."""
    if isinstance(value, (list, tuple)):
        found: list[str] = []
        for item in value:
            found.extend(claims(item))
        return found
    if isinstance(value, dict) and "decision" in value:
        said = [str(value.get(field) or "").strip() for field in DECIDED_FIELDS]
        return [": ".join(part for part in said if part)] if any(said) else []
    return statements(value)


def _clauses(statement: str) -> list[str]:
    return [clause for clause in _CLAUSES.split(statement or "") if clause.strip()]


def _a_denial_of_the_product(clause: str, start: int, end: int) -> bool:
    """Whether the denying words at `clause[start:end]` deny what follows them of the whole product: said near the
    clause's opening, with no condition, outcome or test step before them, and not inside brackets."""
    before = _WORDS.findall(clause[:start])
    if len(before) > _MOST_WORDS_BEFORE or before.count("(") > before.count(")"):
        return False
    return not any(word.lower() in _A_CASE for word in before)


#: What follows a condition: an arrow to its outcome, a status code, a reply. "Without the header -> 401" and "No note
#: has that id. Returns 404" state what happens in one case, not what the product leaves out.
_AN_OUTCOME = re.compile(r"->|\u2192|=>|\b[1-5]\d\d\b|(?i:\b(?:returns?|responds?|answers?)\b)")
#: Words in one item of a left-out list that keep the item's other words in the product: "any feature beyond X".
_KEPT_IN_A_LIST = re.compile(r"(?i)\b(?:beyond|except|other\s+than|besides|apart\s+from|only|instead\s+of|rather\s+than)\b")
_LIST_SEPARATOR = re.compile(r",|;|\bor\b|\band\b|\bnor\b")
#: Words that may stand between a list's separator and the item: "no TLS, no rate limiting", "A, or any X".
_BEFORE_AN_ITEM = re.compile(rf"(?i)^\s*(?:(?:{_NEGATOR}|{_BETWEEN}|other|extra|additional)\s+)*$")


def _left_out_item(clause: str, subject: str) -> int:
    """Where `subject` ends in a clause listing what the product leaves out, or -1: named as an item of the list, not
    inside brackets and not in an item that keeps it ("beyond X", "X only")."""
    named = _mentioning(subject).search(clause)
    if not named:
        return -1
    opening = clause[:named.start()]
    if opening.count("(") > opening.count(")"):
        return -1
    item_start = max([0, *(m.end() for m in _LIST_SEPARATOR.finditer(opening))])
    item_end = _LIST_SEPARATOR.search(clause, named.end())
    item = clause[item_start:item_end.start() if item_end else len(clause)]
    return -1 if _KEPT_IN_A_LIST.search(item) else named.end()


def _denial_end(clause: str, subject: str) -> int:
    """Where a denial of `subject` of the whole product ends in `clause`, or -1 when the clause denies it of no more
    than one case."""
    pattern = _mentioning(subject)
    if _LEFT_OUT.match(clause):
        return _left_out_item(clause, subject)
    before, after = _denying(subject)
    for found in before.finditer(clause):
        if _a_denial_of_the_product(clause, found.start(), found.end()) and not _AN_ACT_ON_IT.match(clause[found.end():]):
            return found.end()
    for found in after.finditer(clause):
        if _a_denial_of_the_product(clause, found.start(), found.start()):
            return found.end()
    # A list after the denying word: "does not implement authentication, search, rate limiting", "no TLS, no X".
    for word in re.finditer(r"(?i)\b(?:no|not|never|without|nor)\b", clause):
        if not _a_denial_of_the_product(clause, word.start(), word.end()):
            continue
        rest = clause[word.end():]
        named = pattern.search(rest)
        if not named:
            continue
        items = _LIST_SEPARATOR.split(rest[:named.start()])
        opening = _WORDS.findall(items[0])
        if opening and opening[0].lower() in _NOT_A_LIST_OF_PARTS:
            continue
        if (len(items) > 1 and _BEFORE_AN_ITEM.match(items[-1])
                and all(len(_WORDS.findall(item)) <= _MOST_WORDS_BETWEEN for item in items[:-1])):
            return word.end() + named.end()
    return -1


def denies(statement: str, subject: str) -> bool:
    """Whether `statement` says the product has no `subject`: "No X", "The service does not support X", "X is not
    supported", "Deferred: ..., X" - a clause about the product, not one case of it ("returns 204 with no X", "if no
    X exists", "without X -> 401")."""
    clauses = _clauses(statement)
    for n, clause in enumerate(clauses):
        end = _denial_end(clause, subject)
        if end >= 0 and not _AN_OUTCOME.search(" ".join([clause[end:], *clauses[n + 1:]])):
            return True
    return False


def states(statement: str, subject: str) -> bool:
    """Whether `statement` says `subject` is part of the product: it names it in a clause with nothing that denies,
    defers or only weighs it."""
    pattern = _mentioning(subject)
    return any(pattern.search(clause) and not _NOT_A_STATEMENT_OF_IT.search(clause) for clause in _clauses(statement))


#: A route as a statement names it, with its method when it has one: `DELETE /notes/{id}`, `/health`.
_A_ROUTE = re.compile(r"(?:\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+)?(?<![\w.])(/[A-Za-z][\w\-/{}:<>]*)")


def _routes(text: str) -> set[str]:
    found = set()
    for method, route in _A_ROUTE.findall(text or ""):
        # A colon after the route ends a heading ("DELETE /notes/{id}: ..."); one inside it names a parameter.
        route = re.sub(r"\{[^}]*\}|<[^>]*>|:[\w-]+", "{}", route.rstrip(":")).rstrip("/.,;:)")
        found.add(f"{method} {route}".strip())
    return found


def _same_route(denied: set[str], stated: set[str]) -> bool:
    """Whether a route the denial names is one the other statement names: the same method and path, or the same path
    where either names no method."""
    for one in denied:
        for other in stated:
            method, _, path = one.rpartition(" ")
            their_method, _, their_path = other.rpartition(" ")
            if path == their_path and (method == their_method or not method or not their_method):
                return True
    return False


#: A statement's heading: the words before its first colon or dash, when they are few.
_A_HEADING = re.compile(r"^\W*(.{1,100}?)\s*(?::\s|\s[\u2014\u2013-]\s|\s\|\s)")
_MOST_HEADING_WORDS = 6


def _named_in_the_heading(statement: str) -> set[str]:
    """The names a statement's heading gives it (`Note.java: ...`, `tasks_api/db.py - ...`): the part it is about."""
    heading = _A_HEADING.match(statement or "")
    if not heading or len(_WORDS.findall(heading.group(1))) > _MOST_HEADING_WORDS:
        return set()
    return {name for name in identifiers(heading.group(1)) if not _A_PLAIN_WORD.fullmatch(name)}


def _opposite(statement: str, their: str, subject: str) -> bool:
    """Whether one of the two denies `subject` of the product and the other states it. A denial said of a route is
    said of that route, and one said under a part's name (`Note.java: ... No business logic`) of that part: each is
    opposite only to a statement about the same route or a statement not headed by another part's name."""
    for denying, stating in ((statement, their), (their, statement)):
        if denies(denying, subject) and states(stating, subject) and not denies(stating, subject):
            routes = _routes(denying)
            if routes and not _same_route(routes, _routes(stating)):
                continue
            part, their_part = _named_in_the_heading(denying), _named_in_the_heading(stating)
            if part and their_part and not part & their_part:
                continue
            return True
    return False


#: A subject that is one plain lower-case word is a word of the language however it is quoted (`limit`, `text`,
#: `create`): a name is a path, a file, a setting or a name with a capital, a dot or an underscore in it.
_A_PLAIN_WORD = re.compile(r"[a-z]+")


def _subjects(statement: str, sections: list[str]) -> list[str]:
    return sorted(subject for subject in identifiers(statement) | phrases(statement, section_names=sections)
                  if not _A_PLAIN_WORD.fullmatch(subject))


def opposite_statements(
    rewritten: dict[str, list[str]], unchanged: dict[str, list[str]],
) -> list[tuple[str, str, str, str, str]]:
    """(subject, rewritten section, its statement, unchanged section, its statement) for each pair saying opposite things.

    Subjects are the names and two-word phrases both statements mention; one statement denies the subject of the
    product (`denies`), the other states it as part of the product (`states`).
    """
    sections = [*rewritten, *unchanged]
    pairs: list[tuple[str, str, str, str, str]] = []
    for section, said in rewritten.items():
        for statement in said:
            subjects = _subjects(statement, sections)
            for other, theirs in unchanged.items():
                for their in theirs:
                    for subject in subjects:
                        if mentions(their, subject) and _opposite(statement, their, subject):
                            pairs.append((subject, section, statement, other, their))
                            break
    return pairs


def _added(before: Any, after: Any) -> list[str]:
    old = set(claims(before))
    return [statement for statement in claims(after) if statement not in old]


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
    unchanged = {name: claims(value) for name, value in after.items() if name not in chosen}
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
    "DECIDED_FIELDS", "ON_BY_DEFAULT", "SAID", "brought_into_line", "claims", "denies", "enabled", "identifiers",
    "opposite_statements", "phrases", "related_block", "related_statements", "states", "statements",
]
