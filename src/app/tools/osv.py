"""Known advisories for exact package releases, from OSV (plan HK.6, LF.1300).

A person checks advisories for what they ship; the harness never saw one (the private search's advisory engine was
asked by no step). OSV answers a batch of `ecosystem/name@version` queries in one request, with no key and no stated
limit; each advisory it names is then read once for its severity and the release that fixed it.

- `advisories(releases)`: for each release, the advisories that affect it - id, aliases, a one-line summary, the
  severity the database states (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or "" when none is stated), the lowest release
  that fixed it above the one asked about, and whether that release is in the same major line.
- Only public package names and versions leave, through the one outbound gate (`app.tools.outbound`): a name holding
  one of the product's own words is not sent, and each request is one `outbound` record.
- A refusal, no network, or an unreadable answer raises `public_data.NotKnown`: the caller says "not known", never
  "none".

Which name OSV gives each ecosystem is the one table here (`ECOSYSTEM`); the harness's ecosystems are the registry
readers' (`app.tools.package_registry`).
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.tools.public_data import NotKnown, ask

logger = logging.getLogger(__name__)

SOURCE = "osv"
#: How the outbound record names the channel.
CHANNEL = "advisories"
HOST = "api.osv.dev"
BATCH = f"https://{HOST}/v1/querybatch"
ADVISORY = f"https://{HOST}/v1/vulns/"
#: Queries in one batch (OSV's own limit is 1,000).
MOST_IN_A_BATCH = 1_000
#: Advisories read for their details in one call; the rest are named with their id alone.
MOST_DETAILS = 40
AT_ONCE = 8
#: Seconds an advisory's details are kept (HK.12: advisories six hours).
KEPT_FOR = 6 * 3_600.0

#: OSV's name of each of the harness's ecosystems.
ECOSYSTEM = {"npm": "npm", "pypi": "PyPI", "crates": "crates.io", "go": "Go", "maven": "Maven",
             "rubygems": "RubyGems", "packagist": "Packagist", "nuget": "NuGet"}

#: Severities in order; "MODERATE" is GitHub's word for medium.
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_SAME_SEVERITY = {"MODERATE": "MEDIUM", "IMPORTANT": "HIGH"}


@dataclass(frozen=True)
class Release:
    ecosystem: str
    name: str
    version: str


@dataclass
class Advisory:
    id: str
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    severity: str = ""
    fixed: str = ""
    same_major: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "aliases": self.aliases, "summary": self.summary, "severity": self.severity,
                "fixed": self.fixed, "same_major": self.same_major}


def rank(severity: str) -> int:
    """0 for none stated, 1 (low) to 4 (critical)."""
    word = _SAME_SEVERITY.get(str(severity or "").upper(), str(severity or "").upper())
    return SEVERITIES.index(word) + 1 if word in SEVERITIES else 0


def _numbers(version: str) -> tuple[int, ...]:
    from app.tools.release_fit import numbers

    return numbers(str(version or "").lstrip("vV"))


def same_major(version: str, fixed: str) -> bool:
    """Whether `fixed` is in `version`'s major line (for a 0.x release, its minor line)."""
    have, want = _numbers(version), _numbers(fixed)
    if not have or not want or have[0] != want[0]:
        return False
    return have[0] != 0 or (len(have) > 1 and len(want) > 1 and have[1] == want[1])


def _normal(ecosystem: str, name: str) -> str:
    name = str(name or "").strip().lower()
    return re.sub(r"[-_.]+", "-", name) if ecosystem == "pypi" else name


def _severity(detail: dict) -> str:
    """The severity the advisory states: the database's own word, then an affected package's."""
    words = [str((detail.get("database_specific") or {}).get("severity") or "")]
    for affected in detail.get("affected") or []:
        if isinstance(affected, dict):
            words.append(str((affected.get("ecosystem_specific") or {}).get("severity") or ""))
            words.append(str((affected.get("database_specific") or {}).get("severity") or ""))
    best = max(words, key=rank)
    return _SAME_SEVERITY.get(best.upper(), best.upper()) if rank(best) else ""


def _fixed(detail: dict, release: Release) -> str:
    """The lowest release above `release` that the advisory names as fixing it; "" when it names none."""
    have = _numbers(release.version)
    found: list[str] = []
    for affected in detail.get("affected") or []:
        package = (affected or {}).get("package") or {}
        if _normal(release.ecosystem, package.get("name")) != _normal(release.ecosystem, release.name):
            continue
        for span in affected.get("ranges") or []:
            for event in (span or {}).get("events") or []:
                fixed = str((event or {}).get("fixed") or "")
                if fixed and _numbers(fixed) and (not have or _numbers(fixed) > have):
                    found.append(fixed)
    return min(found, key=_numbers) if found else ""


def _withheld(releases: list[Release], root: str | Path | None) -> tuple[list[Release], int]:
    """The releases whose names may leave (no word of the product's own in them), and how many were kept back."""
    from app.tools import outbound

    private, keep = outbound.private_words(root), outbound.public_names(root)
    sent = [r for r in releases if not outbound.without_private_words(r.name, private, keep)[1]]
    return sent, len(releases) - len(sent)


def advisories(releases: Iterable[Release], root: str | Path | None = None) -> dict[Release, list[Advisory]]:
    """For each release OSV knows an advisory for, those advisories (releases with none are absent). Raises
    `NotKnown` when OSV could not be asked or did not answer."""
    wanted = list(dict.fromkeys(r for r in releases if r.ecosystem in ECOSYSTEM and r.name and r.version))
    sent, kept_back = _withheld(wanted, root)
    sent = sent[:MOST_IN_A_BATCH]
    if not sent:
        return {}
    queries = [{"package": {"name": r.name, "ecosystem": ECOSYSTEM[r.ecosystem]},
                "version": r.version.lstrip("vV") if r.ecosystem == "go" else r.version} for r in sent]
    answer = ask(SOURCE, BATCH, {"queries": queries}, channel=CHANNEL,
                 said=", ".join(f"{r.name} {r.version}" for r in sent), removed=kept_back)
    results = (answer or {}).get("results") if isinstance(answer, dict) else None
    if not isinstance(results, list):
        raise NotKnown(f"{SOURCE} answered with no results")
    named: dict[Release, list[str]] = {}
    for release, result in zip(sent, results):
        ids = [str(v.get("id")) for v in (result or {}).get("vulns") or [] if isinstance(v, dict) and v.get("id")]
        if ids:
            named[release] = ids
    every = list(dict.fromkeys(i for ids in named.values() for i in ids))
    details = _details(every[:MOST_DETAILS])
    found: dict[Release, list[Advisory]] = {}
    for release, ids in named.items():
        kept: list[Advisory] = []
        for advisory_id in ids:
            detail = details.get(advisory_id) or {}
            aliases = [str(a) for a in detail.get("aliases") or []]
            same = next((a for a in kept if advisory_id in a.aliases or set(aliases) & {a.id, *a.aliases}), None)
            fixed = _fixed(detail, release) if detail else ""
            severity = _severity(detail) if detail else ""
            if same is not None:
                # One advisory under two databases' ids (a PYSEC and a GHSA): one entry, the stronger facts kept.
                same.aliases = list(dict.fromkeys([*same.aliases, advisory_id, *aliases]))
                if rank(severity) > rank(same.severity):
                    same.severity = severity
                if fixed and (not same.fixed or _numbers(fixed) > _numbers(same.fixed)):
                    same.fixed, same.same_major = fixed, same_major(release.version, fixed)
                continue
            summary = " ".join(str(detail.get("summary") or detail.get("details") or "").split())[:160]
            kept.append(Advisory(advisory_id, [a for a in aliases if a != advisory_id], summary, severity, fixed,
                                 same_major(release.version, fixed) if fixed else False))
        found[release] = kept
    return found


def _details(ids: list[str]) -> dict[str, dict]:
    """Each advisory's record, read once and kept; one that cannot be read is left out (its id is still named)."""
    if not ids:
        return {}

    def read(advisory_id: str) -> dict:
        try:
            got = ask(SOURCE, ADVISORY + advisory_id, channel=CHANNEL, said=advisory_id, kept_for=KEPT_FOR)
            return got if isinstance(got, dict) else {}
        except NotKnown:
            return {}

    with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
        return dict(zip(ids, pool.map(read, ids)))


__all__ = ["Advisory", "CHANNEL", "ECOSYSTEM", "HOST", "NotKnown", "Release", "SEVERITIES", "SOURCE", "advisories",
           "rank", "same_major"]
