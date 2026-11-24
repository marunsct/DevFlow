"""A site's robots.txt read as RFC 9309 says, and kept per host for a day (plan KS.7, LF.1297).

Python's standard parser compares a rule's path as a plain prefix: `*` and `$` are taken literally, so GitHub's
`Disallow: /*/tree/` was never applied and the reader answered "allowed" for every tree page (checked 2026-11-24). It
was also fetched again on every read, twice when a page redirected. Here:

- the group whose user agent names the reader's product token is obeyed, every such group combined; with none, the
  `*` groups; with neither, everything is allowed;
- a rule's path may hold `*` (any run of characters) and end in `$` (the address ends there); of the rules that match,
  the longest wins, and an allow wins a tie; an empty `Disallow:` allows; `/robots.txt` itself is always allowed;
- what a site answered is kept per host for `KEPT_SECONDS` (RFC 9309 allows a day): a robots.txt read, or a missing one
  (4xx: everything allowed). An unreachable one (5xx, no answer) refuses the read and is asked again next time.

The cache belongs to the transport that fetched the file (`allows(..., cache_for=...)`): one transport's answers are
never another's.
"""

from __future__ import annotations

import re
import threading
import time
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit

#: Seconds a site's robots.txt is kept (RFC 9309 section 2.4: no more than 24 hours).
KEPT_SECONDS = 24 * 3600
#: Bytes of a robots.txt read (RFC 9309 section 2.5: at least 500 kibibytes).
MOST_BYTES = 500 * 1024

#: What a path keeps encoded and what it decodes, so a rule and an address compare alike.
_SAFE = "/?=&;:@!$'()*+,~-._"


def _normal(path: str) -> str:
    return quote(unquote(path), safe=_SAFE)


@dataclass(frozen=True)
class Rule:
    allow: bool
    path: str
    pattern: re.Pattern[str]


def _rule(allow: bool, path: str) -> Rule:
    anchored = path.endswith("$")
    body = _normal(path[:-1] if anchored else path)
    pattern = ".*".join(re.escape(part) for part in body.split("*")) + (r"\Z" if anchored else "")
    return Rule(allow, path, re.compile(pattern, re.S))


@dataclass
class Rules:
    """One robots.txt: its groups as (user agents, rules)."""

    groups: list[tuple[list[str], list[Rule]]] = field(default_factory=list)

    def _rules_for(self, agent: str) -> list[Rule] | None:
        token = agent.split("/", 1)[0].strip().lower()
        mine = [rules for agents, rules in self.groups if token in agents]
        if mine:
            return [rule for rules in mine for rule in rules]
        anyone = [rules for agents, rules in self.groups if "*" in agents]
        return [rule for rules in anyone for rule in rules] if anyone else None

    def allows(self, agent: str, url: str) -> bool:
        """Whether `agent` may read `url` (its path and query) under these rules."""
        parts = urlsplit(str(url or ""))
        path = _normal(parts.path or "/") + (("?" + _normal(parts.query)) if parts.query else "")
        if path == "/robots.txt":
            return True
        rules = self._rules_for(agent)
        if not rules:
            return True
        best: Rule | None = None
        for rule in rules:
            if not rule.pattern.match(path):
                continue
            if best is None or len(rule.path) > len(best.path) or (
                    len(rule.path) == len(best.path) and rule.allow and not best.allow):
                best = rule
        return best is None or best.allow


def parse(text: str) -> Rules:
    """The groups of a robots.txt's text: consecutive `User-agent` lines open a group, the rules after them are its."""
    groups: list[tuple[list[str], list[Rule]]] = []
    agents: list[str] = []
    rules: list[Rule] = []
    in_rules = False
    for raw in str(text or "")[:MOST_BYTES].splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.split("/", 1)[0].strip().lower())
        elif key in {"allow", "disallow"} and agents:
            in_rules = True
            if value:  # an empty Disallow allows everything; an empty Allow says nothing
                rules.append(_rule(key == "allow", value if value.startswith(("/", "*")) else "/" + value))
    if agents:
        groups.append((agents, rules))
    return Rules(groups)


#: What one host answered: (when, its rules), or (when, None) for a missing robots.txt (everything allowed).
_Kept = tuple[float, "Rules | None"]
_CACHES: "weakref.WeakKeyDictionary[Any, dict[str, _Kept]]" = weakref.WeakKeyDictionary()
_LOCK = threading.Lock()

#: (status, the file's text) for a robots.txt address, or None when it could not be reached.
RobotsGet = Callable[[str], "tuple[int, str] | None"]


def _site(url: str) -> str:
    parts = urlsplit(str(url or ""))
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def allows(url: str, agent: str, get: RobotsGet, *, cache_for: Any, now: Callable[[], float] = time.time) -> bool:
    """Whether the site's robots.txt lets `agent` read `url`, its file asked through `get` once per host and kept
    `KEPT_SECONDS` for the transport `cache_for`. A robots.txt that cannot be reached (no answer, 5xx) refuses."""
    site = _site(url)
    with _LOCK:
        try:
            kept = _CACHES.setdefault(cache_for, {})
        except TypeError:  # a transport that cannot be weakly referenced is never cached for
            kept = {}
        found = kept.get(site)
    if found is None or now() - found[0] > KEPT_SECONDS:
        try:
            answer = get(site + "/robots.txt")
        except Exception:  # noqa: BLE001 - unreachable: RFC 9309 says assume it disallows
            answer = None
        if answer is None or answer[0] >= 500:
            return False
        status, text = answer
        found = (now(), parse(text) if 200 <= status < 300 else None)
        with _LOCK:
            kept[site] = found
    rules = found[1]
    return True if rules is None else rules.allows(agent, url)


__all__ = ["KEPT_SECONDS", "Rules", "allows", "parse"]
