"""Each interface contract line's criterion id checked against the criterion it names (deep review 2026-11-25, item 1).

The interface contract is handed to every builder and fixer "word for word", and the release titles each probe
`[AC-n] contract ...` and charges its failure to that criterion. Measured over 15 runs: in 7 the architect numbered
the lines 1..n instead of naming the criterion each serves - `AC-2 POST /signup -> 409` where AC-2 is "Sign in",
`AC-6 POST /api/register -> 201` where AC-6 is "Task categories and tags" - and the same request then told the fixer
AC-6 was a later sprint's work. Nothing compared a line with the criterion it named.

So, when the specification is written, each line is compared with the criterion it names, by what the line is about:
an HTTP line's route, a page line's path and control name, a command line's arguments and exit status. A line whose
named criterion says nothing of it is unrelated, and then:

- one other criterion that states the line's own route, control or command (failing that, the one other criterion
  whose words it shares) names it instead: the id is corrected;
- otherwise, when the contract's ids run 1, 2, 3 ... down its lines - numbered by line, not by criterion - the id is
  taken off, and the line is checked at release charging no criterion (`interface_contract.parse` reads a line with
  none);
- otherwise the line is left as written: a criterion can be about a route in other words ("Sign in" for `/login`).

A line naming several criteria, or one with no subject to compare, is left as written. Never raises.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: The id a line opens with, alone (`AC-6 POST ...`); a line naming several is not judged.
_ONE_LEADING_ID = re.compile(r"^(\s*[-*`\"']*\s*)((?:AC|CR)-(\d+))(\s*:?\s+)(?!(?:AC|CR)-\d)")
#: A route parameter in any spelling: `{id}`, `:id`, `<id>`.
_A_PARAMETER = re.compile(r"\{[^}]*\}|<[^>]*>|(?<=/):[\w-]+")
#: Path segments that say nothing of what a route is for.
_SAYS_NOTHING = frozenset({"api", "index", "html", "www", "app"})
_A_VERSION_SEGMENT = re.compile(r"^v\d+$")
#: A placeholder in a command line: `<file>`, `N`, `-`.
_A_PLACEHOLDER = re.compile(r"^(?:<[^>]*>|[A-Z]{1,3}|-+|\.+)$")


@dataclass
class Checked:
    """The contract lines after the check, and a sentence for each line changed."""

    lines: list[str]
    corrected: list[str] = field(default_factory=list)
    taken_off: list[str] = field(default_factory=list)


def _stem(word: str) -> str:
    word = word.lower()
    if len(word) > 4 and word.endswith("s"):
        word = word[:-1]
    return word[:6]


def _joined(text: str) -> str:
    """`text` lower-cased with everything but letters and digits removed: "Sign up" and `/signup` meet."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z0-9]+", str(text or "")) if len(w) >= 3]


def _path_words(path: str) -> list[str]:
    """The words of a route's segments and of its query's names: `/api/bookmarks?tag=<value>` -> bookmarks, tag."""
    route, _, query = str(path or "").partition("?")
    words = [w for name in re.findall(r"([A-Za-z][\w-]*)=", query) for w in _words(name)]
    for segment in _A_PARAMETER.sub("", route).split("/"):
        segment = segment.strip()
        if not segment or segment.lower() in _SAYS_NOTHING or _A_VERSION_SEGMENT.match(segment.lower()):
            continue
        words += [w for w in _words(segment) if w.lower() not in _SAYS_NOTHING]
    return words


def _normal_route(text: str) -> str:
    return _A_PARAMETER.sub("{}", str(text or ""))


@dataclass
class _Subject:
    """What one line is about: the words to find in a criterion, and the literal phrases that state it."""

    stems: list[str]
    #: The phrases that state the line exactly, strongest first (`POST /signup`, then `/signup`).
    literals: list[str]
    exit_code: int = 0
    #: Words that only break a tie between criteria: a page line's path, after its control's name.
    lesser: list[str] = field(default_factory=list)


def _subject(check: Any) -> _Subject | None:
    if check.kind == "http":
        route = _normal_route(check.path.split("?", 1)[0]).rstrip("/") or "/"
        words = _path_words(check.path)
        literals = [f"{check.method} {route}"] + ([route] if route != "/" else [])
        return _Subject([_stem(w) for w in words], literals) if words or route != "/" else None
    if check.kind == "page":
        # By its control's name: every control on `/tasks` shares that path, and so does every criterion about it.
        name = str(check.name or "").strip()
        named, path = _words(name), _path_words(check.path)
        if not named and not path:
            return None
        return _Subject([_stem(w) for w in named or path], [f'"{name}"', name] if name else [],
                        lesser=[_stem(w) for w in path] if named else [])
    if check.kind == "command":
        parts = str(check.command or "").split()
        rest = [p for p in parts[1:] if not _A_PLACEHOLDER.match(p) and p not in ("-m",)]
        words = [w for p in rest for w in _words(p.lstrip("-"))]
        flags = [p for p in rest if p.startswith("--")]
        literals = [" ".join(parts)] + flags if parts else []
        if not words and not check.exit_code:
            return None
        return _Subject([_stem(w) for w in words], literals, int(check.exit_code or 0))
    return None


def _shares_a_word(subject: _Subject, text: str) -> int:
    joined = _joined(text)
    return sum(1 for stem in dict.fromkeys(subject.stems) if len(stem) >= 3 and stem in joined)


def _says_its_exit_status(subject: _Subject, text: str) -> bool:
    return bool(subject.exit_code) and bool(
        re.search(rf"\b(?:exit|exits|status)\b\D{{0,20}}\b{subject.exit_code}\b", str(text or ""), re.I))


def _related(subject: _Subject, text: str) -> bool:
    return bool(_shares_a_word(subject, text)) or _says_its_exit_status(subject, text) or any(
        _states(literal, text) for literal in subject.literals)


def _states(literal: str, text: str) -> bool:
    """Whether `text` states `literal` as itself, not as the start of a longer route or word."""
    if not literal:
        return False
    plain = _normal_route(" ".join(str(text or "").split()))
    return bool(re.search(r"(?<![\w/-])" + re.escape(literal) + r"(?![\w/-])", plain, re.I))


def _the_one_that_states_it(subject: _Subject, criteria: dict[str, str], named: str) -> str:
    """The id of the one other criterion that states the line (by its strongest literal, then by its words); ""."""
    others = {ident: text for ident, text in criteria.items() if ident != named}
    for literal in subject.literals:
        stating = [ident for ident, text in others.items() if _states(literal, text)]
        if len(stating) == 1:
            return stating[0]
        if stating:
            return ""
    by_words = {ident: 10 * _shares_a_word(subject, text) + _shares_a_word(_Subject(subject.lesser, []), text)
                for ident, text in others.items()}
    best = max(by_words.values(), default=0)
    sharing = [ident for ident, count in by_words.items() if count and count == best]
    if len(sharing) == 1:
        return sharing[0]
    if subject.exit_code:
        stating = [ident for ident, text in others.items() if _says_its_exit_status(subject, text)]
        if len(stating) == 1 and not best:
            return stating[0]
    return ""


def _numbered_by_line(numbers: list[int]) -> bool:
    """Whether the ids run 1, 2, 3 ... down the lines (a group of lines may share one): numbered by line."""
    if len(numbers) < 3 or numbers[0] != 1:
        return False
    return all(later - earlier in (0, 1) for earlier, later in zip(numbers, numbers[1:])) and numbers[-1] > 2


def checked(lines: Iterable[Any], criteria: Iterable[Any]) -> Checked:
    """`lines` with each criterion id that names an unrelated criterion corrected or taken off. Never raises."""
    given = [str(line) for line in lines or ()]
    try:
        from app.acceptance.interface_contract import parse

        texts = {str(getattr(c, "id", "") or ""): str(getattr(c, "text", "") or "") for c in criteria or ()}
        texts = {ident: text for ident, text in texts.items() if ident}
        if not texts:
            return Checked(given)
        judged: list[tuple[int, re.Match[str], _Subject, str]] = []
        numbers: list[int] = []
        for at, line in enumerate(given):
            leading = _ONE_LEADING_ID.match(line)
            if not leading:
                continue
            numbers.append(int(leading.group(3)))
            checks, _ = parse([line])
            subject = _subject(checks[0]) if len(checks) >= 1 else None
            if subject is None:
                continue
            named = leading.group(2)
            if not _related(subject, texts.get(named, "")):
                judged.append((at, leading, subject, named))
        result = Checked(list(given))
        by_line = _numbered_by_line(numbers)
        for at, leading, subject, named in judged:
            line = given[at]
            instead = _the_one_that_states_it(subject, texts, named)
            what = f"\"{texts[named][:80]}\"" if named in texts else "no criterion of this product"
            if instead:
                result.lines[at] = line[:leading.start(2)] + instead + line[leading.end(2):]
                result.corrected.append(f"`{line.strip()}`: {named} is {what}; {instead} states it - corrected to {instead}")
            elif by_line:
                result.lines[at] = line[:leading.start(2)] + line[leading.end(4):]
                result.taken_off.append(f"`{line.strip()}`: {named} is {what}, and the ids are numbered by line - "
                                        "the id is taken off")
        return result
    except Exception:  # noqa: BLE001 - the lines as written, as before
        logger.debug("Could not check the contract's criterion ids", exc_info=True)
        return Checked(given)


def with_the_ids_checked(specification: Any, criteria: Iterable[Any]) -> Any:
    """`specification` with its interface contract's ids checked against `criteria` (`checked`). Never raises."""
    try:
        lines = list(getattr(specification, "interface_contract", None) or [])
        if not lines or not hasattr(specification, "model_copy"):
            return specification
        result = checked(lines, list(criteria or ()))
        if result.lines == [str(line) for line in lines]:
            return specification
        for change in result.corrected + result.taken_off:
            logger.info("Interface contract: %s", change)
        if result.taken_off:
            from app.observability.rule_coverage import CONTRACT_IDS, could_not_apply

            could_not_apply(CONTRACT_IDS, f"{len(result.taken_off)} line(s) named an unrelated criterion and no other "
                                          f"criterion states them; first: {result.taken_off[0]}")
        return specification.model_copy(update={"interface_contract": result.lines})
    except Exception:  # noqa: BLE001 - the specification as written
        logger.debug("Could not check the specification's contract ids", exc_info=True)
        return specification


__all__ = ["Checked", "checked", "with_the_ids_checked"]
