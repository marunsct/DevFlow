"""A limit the specification puts on how often one client may call, reconciled with the suite before it is locked.

Measured on one medium-brief run: the brief asked for no rate limit, a security specialist's advice was adopted into the
specification ("registration attempts exceed 10 per hour per IP", "login attempts exceed 5 per minute per IP"), and the
locked suite, run from one address against one service, signed up about 88 times and signed in about 92 times a run.
Every test past the tenth sign-up was refused 429 for 22 hours; a fixer named the collision and could do nothing, since
the specification mandated the limit and the suite was locked. Nothing had checked that the two could both be true.

So before the lock the harness reads, with no model:

1. the specification's limits on how often one client may call (`limits_in`): a count in a window - "10 per hour",
   "5/min" - in a sentence that says it limits, with the operation it limits and whom it counts per (an address, or a
   user, an account or a key). Conservative: prose that only mentions a rate, a limit with no window, a lockout after
   failures, or an operation the suite's addresses cannot be matched to, is no limit here;
2. how often the suite calls that operation from one client in one run (`calls_in_the_suite`): the requests to that
   route its files make, through shared helpers, hooks and fixtures too, read by the reader of the suite's language
   (`_javascript.client_calls`, `_python.client_calls`);
3. when the suite calls more often than the limit allows within its window, one finding for the specification, not
   the suite (`reconcile_before_the_lock`): a ruling every later stage reads with the specification's other rulings -
   the limit is declined for this release when the brief does not ask for it, else its count is read from
   `ENVIRONMENT_NAME`, which the acceptance start gives the product (every command the harness or a stage runs to
   test it gets it, and the pack's start for the suite passes it on to the product it starts). A specification with
   no such limit, or a suite within it, is left exactly as it was.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The variable a limit on how often one client may call reads its count from.
ENVIRONMENT_NAME = "CLIENT_RATE_LIMIT"
#: The least count the acceptance start gives: room for a suite that grows after the lock.
LEAST_COUNT_GIVEN = 1_000
#: Where the reconciliation is kept: the environment the acceptance start gives, and why.
RECORD_FILE = ".harness/client_limits.json"
#: How long one test is taken to run when a run of the suite is spread over a window shorter than the run. A slow
#: guess on purpose: the slower the run, the fewer calls fall in one window, the fewer limits are found too tight.
SECONDS_PER_TEST = 3.0

#: The specification's sections a limit on calling is written in, when it has sections.
_SECTIONS = ("security_and_privacy", "reliability_and_observability", "api_and_event_contracts", "interface_contract")

_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60, "minute": 60,
          "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "d": 86400, "day": 86400,
          "days": 86400}
_LONG_UNIT = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)"
#: A count in a window: "10 per hour", "5 attempts per 15 minutes", "100 requests/min", "5 logins a minute".
_A_COUNT_IN_A_WINDOW = re.compile(
    r"(?<![\w.%$])(?P<count>\d{1,6})(?![\d.%])\s*(?:[A-Za-z][A-Za-z-]*\s+){0,3}?"
    r"(?:/\s*(?:(?P<span1>\d{1,4})\s*)?(?P<unit1>" + _LONG_UNIT + r"|[smhd])"
    r"|(?:per|every|each|an?|in(?:\s+(?:an?|one))?)\s+(?:(?P<span2>\d{1,4})\s*)?(?P<unit2>" + _LONG_UNIT + r"))\b",
    re.IGNORECASE)
#: A sentence that sets a limit says so; one that only mentions a rate does not.
_SAYS_IT_LIMITS = re.compile(
    r"\b(?:rate[- ]?limit\w*|throttl\w*|limit\w*|exceed\w*|at most|no more than|up to|maximum|max|429|too many|"
    r"quota\w*|allow\w*|capped)\b", re.IGNORECASE)
_PER_A_USER = re.compile(
    r"\b(?:per|each|by)\s+(?:user|users|account|accounts|e-?mail|username|api[- ]?key|key|token|session|device)\b",
    re.IGNORECASE)
#: A route written in the sentence: `POST /api/auth/register`.
_A_ROUTE = re.compile(r"(?:^|(?<=[\s`'\"(]))(/[A-Za-z0-9_\-/{}:.]*[A-Za-z0-9_\-}])")
#: Words that say how or how often, not what is called.
_NOT_THE_OPERATION = frozenset("""
    a an the to of at in on for by from per each every all any one same total global most max maximum no more than up
    is are be been when if then after before must should will shall may can allow allowed allows limit limits limited
    limiting rate ratelimit ratelimited ratelimiting throttle throttled throttling exceed exceeds exceeded exceeding
    return returns respond responds answer answers reject rejects rejected refuse refuses refused with status http
    too many requests request calls call api attempts attempt tries try times time and or not ip ips address addresses
    client clients host origin user users account accounts email username key keys token tokens session sessions
    device source remote second seconds sec secs minute minutes min mins hour hours hr hrs day days window windows
    sliding fixed quota quotas capped cap error errors code header headers retry after later than that this those
    these which who whose where
""".split())
#: Names one operation goes by: a word of the specification and a route's last part are the same operation when both
#: fall in one group.
_SAME_OPERATION = (
    frozenset({"register", "registers", "registration", "registrations", "signup", "signups", "enrol", "enroll",
               "enrolment", "enrollment"}),
    frozenset({"login", "logins", "signin", "signins", "logon", "logons"}),
)
_REQUESTS_OF_ANY_KIND = re.compile(r"\b(?:requests?|calls?|api)\b", re.IGNORECASE)
_THE_BRIEF_ASKS = re.compile(
    r"\b(?:rate[- ]?limit\w*|throttl\w*|lock(?:s|ed)?\s+out|lockouts?|brute[- ]force|too many (?:requests|attempts)|"
    r"429)\b", re.IGNORECASE)
_A_STRING = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`")


@dataclass(frozen=True)
class Limit:
    """One limit on how often one client may call, as the specification writes it."""

    sentence: str
    count: int
    #: The window, in seconds, and as the sentence names it ("hour", "15 minutes").
    window: int
    window_said: str
    #: "address" (one machine: per IP, per client, or unsaid) or "user" (per user, account or key).
    per: str
    #: The words naming what it limits ("registration"), and a route the sentence writes; neither for every request.
    words: tuple[str, ...]
    route: str = ""

    @property
    def of_every_request(self) -> bool:
        return not self.words and not self.route


@dataclass(frozen=True)
class Collision:
    """A limit the suite calls past: how often, and where."""

    limit: Limit
    #: The route the suite calls, as its code most often writes it ("" for every request).
    called: str
    total: int
    most_in_one_test: int
    in_one_window: int


def _plain(text: str) -> str:
    return " ".join(str(text or "").split())


def _lines(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [line for item in value for line in _lines(item)]
    return [str(value)] if value not in (None, "") else []


def the_specification_s_text(specification: Any, root: str | Path | None = None) -> str:
    """The sections of the specification a limit on calling is written in; the whole text when it has no sections."""
    if specification is None:
        path = Path(root or ".") / "docs" / "technical_specification.md"
        return path.read_text(encoding="utf-8", errors="replace") if root and path.is_file() else ""
    if isinstance(specification, str):
        return specification
    if isinstance(specification, dict):
        found = [specification.get(name) for name in _SECTIONS]
    else:
        found = [getattr(specification, name, None) for name in _SECTIONS]
    return "\n".join(line for value in found for line in _lines(value))


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in str(text or "").splitlines():
        parts.extend(re.split(r"(?<=[.;!?])\s+(?=[A-Z(`\"'])", line.strip(" -*\t")))
    return [_plain(part) for part in parts if part.strip()]


def _compact(text: str) -> str:
    """`text` lower-cased with one operation's spellings made one word: "sign-up", "sign up" -> "signup"."""
    text = text.lower()
    text = re.sub(r"\bsign[\s_-]?up", "signup", text)
    text = re.sub(r"\bsign[\s_-]?in", "signin", text)
    text = re.sub(r"\blog[\s_-]?in", "login", text)
    text = re.sub(r"\blog[\s_-]?on", "logon", text)
    return text


def _operation_words(text: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z][a-z-]*", _compact(re.sub(_A_ROUTE, " ", text)))
    return tuple(dict.fromkeys(w.strip("-") for w in words if w.strip("-") and w.strip("-") not in _NOT_THE_OPERATION))


def limits_in(text: str) -> list[Limit]:
    """Each limit on how often one client may call that `text` sets, as written; [] when it sets none."""
    found: list[Limit] = []
    for sentence in _sentences(text):
        if not _SAYS_IT_LIMITS.search(sentence):
            continue
        matches = list(_A_COUNT_IN_A_WINDOW.finditer(sentence))
        for index, match in enumerate(matches):
            unit = (match.group("unit1") or match.group("unit2") or "").lower()
            span = int(match.group("span1") or match.group("span2") or 1)
            count = int(match.group("count"))
            if unit not in _UNITS or not count or not span:
                continue
            before = sentence[matches[index - 1].end() if index else 0:match.start()]
            after = sentence[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(sentence)]
            own = f"{before} {match.group(0)} {after}"
            words = _operation_words(before) or _operation_words(after.split(",")[0])
            route = next(iter(_A_ROUTE.findall(before) or _A_ROUTE.findall(after)), "")
            if not words and not route and not _REQUESTS_OF_ANY_KIND.search(own):
                continue
            found.append(Limit(
                sentence=sentence[:400], count=count, window=span * _UNITS[unit],
                window_said=(f"{span} {unit}" if span > 1 else unit.rstrip("s") if len(unit) > 1 else
                             {"s": "second", "m": "minute", "h": "hour", "d": "day"}[unit]),
                per="user" if _PER_A_USER.search(after[:60] + " " + before) else "address",
                words=words, route=route,
            ))
    return found


def _last_part(address: str) -> str:
    """The last named part of an address: `${BASE}/auth/register?x=1` -> "register"; "" for none."""
    for part in reversed(re.split(r"[/?#]", address.split("?")[0].split("#")[0])):
        part = part.strip()
        if not part or part[0] in ":{<[$" or part.isdigit() or not re.search(r"[A-Za-z]", part):
            continue
        return re.sub(r"[-_]", "", part.lower())
    return ""


def _the_same_operation(part: str, word: str) -> bool:
    word = re.sub(r"[-_]", "", word.lower())
    if not part or not word:
        return False
    if part == word or any(part in group and word in group for group in _SAME_OPERATION):
        return True
    return len(part) >= 5 and len(word) >= 5 and part[:5] == word[:5]


def address_matcher(limit: Limit) -> Callable[[str], bool] | None:
    """Whether a string in the suite is an address of the operation `limit` limits; None for every request."""
    if limit.of_every_request:
        return None
    wanted = (*limit.words, *([_last_part(limit.route)] if limit.route else []))

    def names_it(text: str) -> bool:
        if "/" not in text or re.search(r"\s", text) or len(text) > 300:
            return False
        part = _last_part(text)
        return any(_the_same_operation(part, word) for word in wanted if word)

    return names_it


def _readers() -> dict[str, Callable[[Sequence[str], Callable[[str], bool] | None], tuple[list[int], int]]]:
    """The reader of a suite file by its language, by its name's ending."""
    from app.stacks.packs import _javascript, _python

    return {**dict.fromkeys((".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"), _javascript.client_calls),
            ".py": _python.client_calls}


def calls_in_the_suite(files: dict[str, str], limit: Limit) -> tuple[list[int], int, str]:
    """(the calls each test makes to what `limit` limits, the calls made once a run, the route as most often written)."""
    matcher = address_matcher(limit)
    readers = _readers()
    by_reader: dict[Any, list[str]] = {}
    for name, text in files.items():
        reader = readers.get(Path(name).suffix.lower())
        if reader is not None:
            by_reader.setdefault(reader, []).append(text)
    per_test: list[int] = []
    once = 0
    for reader, texts in by_reader.items():
        each, shared = reader(texts, matcher)
        per_test.extend(each)
        once += shared
    written: Counter[str] = Counter()
    if matcher is not None:
        for text in files.values():
            written.update(literal[1:-1] for literal in _A_STRING.findall(text) if matcher(literal[1:-1]))
    return per_test, once, (written.most_common(1)[0][0] if written else "")


def _in_one_window(limit: Limit, per_test: list[int], once: int) -> int:
    total, most = sum(per_test) + once, max(per_test, default=0)
    if limit.per == "user":
        return most
    run = max(1, len(per_test)) * SECONDS_PER_TEST
    return total if limit.window >= run else max(most, math.ceil(total * limit.window / run))


def collisions(specification_text: str, files: dict[str, str]) -> list[Collision]:
    """Each limit of the specification the suite calls past within the limit's window; [] for none."""
    found: list[Collision] = []
    for limit in limits_in(specification_text):
        per_test, once, called = calls_in_the_suite(files, limit)
        if not per_test and not once:
            continue
        within = _in_one_window(limit, per_test, once)
        if within > limit.count:
            found.append(Collision(limit=limit, called=called, total=sum(per_test) + once,
                                   most_in_one_test=max(per_test, default=0), in_one_window=within))
    return found


def the_brief_asks_for_a_limit(brief: str) -> bool:
    """Whether the brief itself asks that a client be refused for calling too often."""
    return bool(limits_in(brief) or _THE_BRIEF_ASKS.search(str(brief or "")))


def count_given(found: Sequence[Collision]) -> int:
    """The count the acceptance start gives: ten times the most the suite calls within one window, at least
    `LEAST_COUNT_GIVEN`."""
    return max(LEAST_COUNT_GIVEN, 10 * max((c.in_one_window for c in found), default=0))


def the_acceptance_start(root: str | Path) -> str:
    """The pack's start for the suite, named for a builder: the file that starts the product for the suite."""
    try:
        from app.stacks import contract

        found = contract.the_pack(root)
        if found is not None:
            pack, record = found
            project = str(record.get("project") or "").strip("/")
            starts = [f for f in pack.kept_files if re.search(r"(?:^|/)(?:playwright\.config\.\w+|conftest\.py)$", f)]
            where = f"{project}/{starts[0]}" if project and starts else (starts[0] if starts else "")
            if where:
                return f"`{where}`, which starts the product for the suite"
            if pack.acceptance_test:
                return f"`{' '.join(pack.acceptance_test)}`" + (f" in `{project}`" if project else "")
    except Exception:  # noqa: BLE001 - named in general instead
        logger.debug("Could not name the pack's start for the suite", exc_info=True)
    return "the harness's run of the acceptance suite"


def _per(limit: Limit) -> str:
    return "per user" if limit.per == "user" else "per address"


def the_finding(found: Sequence[Collision], *, asked: bool, start: str) -> str:
    """The one finding for the specification: each limit with how often the suite calls past it, and what stands."""
    value = count_given(found)
    lines = [
        "The specification limits how often one client may call, and the acceptance suite, run from one address "
        "against one service, calls more often than that: every test past the limit is refused whatever the product "
        "does, and no fix can change it while both stand."
    ]
    for each in found:
        called = f"`{each.called}`" if each.called else "the service"
        lines.append(
            f"- \"{each.limit.sentence}\" allows {each.limit.count} per {each.limit.window_said} {_per(each.limit)}; "
            f"the suite calls {called} about {each.total} times a run, {each.in_one_window} within one "
            f"{each.limit.window_said}, at most {each.most_in_one_test} in one test.")
    lines.append(the_decision(asked=asked, start=start, value=value))
    return "\n".join(lines)


def the_decision(*, asked: bool, start: str, value: int) -> str:
    """What stands instead of the limit: declined, or read from the environment the acceptance start gives."""
    if asked:
        return (f"The brief asks for this limit, so it stays, with its count read from the environment variable "
                f"`{ENVIRONMENT_NAME}` when it is set and the specification's count when it is not. The acceptance "
                f"start ({start}) runs the product with `{ENVIRONMENT_NAME}={value}`, which the suite fits within; a "
                "release started without it keeps the specification's count. No acceptance test expects a client "
                "to be refused for calling too often.")
    return ("The brief asks for no such limit, so it is declined for this release: the product does not refuse a "
            f"client for how often it calls. A limit kept anyway reads its count from the environment variable "
            f"`{ENVIRONMENT_NAME}`, which the acceptance start ({start}) sets to {value}, so the suite fits within "
            "it. No acceptance test expects a client to be refused for calling too often.")


def _suite_files(root: str | Path) -> dict[str, str]:
    from app.acceptance import suite

    files: dict[str, str] = {}
    for path in suite.suite_files(root):
        try:
            files[str(path)] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return files


def environment(workspace: str | Path) -> dict[str, str]:
    """The environment the acceptance start gives the product: {} unless a limit was reconciled. Never raises."""
    try:
        path = Path(workspace) / RECORD_FILE
        if not path.is_file():
            return {}
        given = json.loads(path.read_text(encoding="utf-8")).get("environment") or {}
        return {str(k): str(v) for k, v in given.items() if re.fullmatch(r"[A-Z_][A-Z0-9_]*", str(k))}
    except Exception:  # noqa: BLE001 - a command without it is a command as before
        return {}


def reconcile_before_the_lock(state: Any, update: dict[str, Any]) -> str:
    """The one finding for the specification when the suite calls past a limit it sets; "" when it does not.

    The finding becomes a ruling on the specification (`specification_rulings.the_harness_rules`) and a decision in
    `update`, read by every later stage with the specification's other rulings; the environment it names is kept for
    the acceptance start (`environment`). Asked again with nothing new, nothing is added. Never raises.
    """
    try:
        root = state["repository"].root_path
        text = the_specification_s_text(state.get("technical_specification"), root)
        if not text.strip() or not _SAYS_IT_LIMITS.search(text):
            return ""
        found = collisions(text, _suite_files(root))
        if not found:
            return ""
        brief = str(getattr(state.get("document"), "text", "") or "")
        asked = the_brief_asks_for_a_limit(brief)
        start = the_acceptance_start(root)
        value = max(count_given(found), int(environment(root).get(ENVIRONMENT_NAME) or 0))
        finding = the_finding(found, asked=asked, start=start)
        path = Path(root) / RECORD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "environment": {ENVIRONMENT_NAME: str(value)},
            "declined": not asked,
            "limits": [{"sentence": c.limit.sentence, "count": c.limit.count, "window_seconds": c.limit.window,
                        "per": c.limit.per, "called": c.called, "calls_a_run": c.total,
                        "calls_in_one_window": c.in_one_window, "most_in_one_test": c.most_in_one_test}
                       for c in found],
            "finding": finding,
        }, indent=2), encoding="utf-8")
        from app.agents import specification_rulings

        ruled = specification_rulings.the_harness_rules(
            state, update,
            question="The specification limits how often one client may call more tightly than the locked suite "
                     "calls: which stands?",
            stands=the_decision(asked=asked, start=start, value=value),
            gives_way="; ".join(dict.fromkeys(c.limit.sentence for c in found)),
            why=finding.splitlines()[0],
        )
        if ruled is not None:
            logger.warning("The suite calls past %d limit(s) the specification sets; ruled for the specification "
                           "before the lock (%s)", len(found), "declined" if not asked else ENVIRONMENT_NAME)
        return finding
    except Exception:  # noqa: BLE001 - the lock goes on as it would have
        logger.warning("Could not reconcile the specification's limits with the suite", exc_info=True)
        return ""
