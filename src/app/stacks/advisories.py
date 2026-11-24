"""Advisories and support dates for what ships, checked after every install (plan HK.6, LF.1300).

A person checks advisories and the support window of what they ship before a release. The harness never did: the
security reviewer read code with no advisory data, and the release had no end-of-life or advisory check
(`reports/research/2026-11-24-agents-that-work-like-a-team.md`, section (b)). Models also pick stale and vulnerable
releases systematically - 36.7-55.7% of tasks with pinned versions carried a known CVE in one ten-model study.

So after an install resolves (`app.stacks.toolchain_fit.after_resolving`), the resolved names and versions go to OSV in
one batch (`app.tools.osv`), and the runtime and each direct dependency that endoflife.date tracks go to its support
cycles (`app.tools.support_dates`). The findings are kept in the stack facts (`.harness/stack-facts.json`, under
`advisories` by folder and `support` by product) and read by:

- the security reviewer: one short section of evidence (`for_the_security_reviewer`) - a shipped dependency at or
  above the bar (`BAR`: high, critical) is a finding whose remediation is the release that fixed it;
- the release (`release_gaps`): a known advisory at or above the bar on a dependency that ships is a gap naming the
  fixed release (`ADVISORY_GAP`, blocking: the product ships a known hole). One on a package for development only
  (`app.analysis.development_only`) does not ship and is a note, never a block (`DEVELOPMENT_ADVISORY`); a runtime or
  framework past its end of support is a note (`PAST_SUPPORT`); a check that could not be made is a note saying so
  (`NOT_KNOWN`).

Nothing is changed for the project: a fixed release in the same major line is named as a bump, one in a new major
line as an upgrade to make with care (the report's rule: only within the same major is a bump safe). A failed
request degrades to "not known" (`public_data.NotKnown`, the KS.3 breaker); the same resolved set is not asked
twice. Part of the stack facts (`STACK_FACTS`, a built-in fix), so off in the tests unless a test turns it on.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The severities at which a shipped advisory is a release gap and a security finding.
BAR = frozenset({"HIGH", "CRITICAL"})
#: Lines of advisories in the security reviewer's section.
MOST_LINES = 12

#: How the release names each kind (`app.completion_verdict` lists all but the first as notes).
ADVISORY_GAP = "A dependency that ships has a known advisory:"
DEVELOPMENT_ADVISORY = "A development-only dependency has a known advisory; it does not ship:"
PAST_SUPPORT = "What the product runs on is past its end of support:"
NOT_KNOWN = "Advisories for what ships are not known:"

HEADING = "--- Advisories and support dates for what ships (`.harness/stack-facts.json`) ---"

KNOWN = "known"


def _where(root: Path, directory: Path) -> str:
    return str(directory.relative_to(root)) if directory != root and directory.is_relative_to(root) else "."


def _digest(resolved: list[Any]) -> str:
    text = "\n".join(sorted(f"{r.ecosystem} {r.name} {r.version}" for r in resolved))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def check(root: str | Path, directory: str | Path) -> dict[str, Any]:
    """What OSV and endoflife.date say of what `directory`'s install resolved: {"state", "digest", "found",
    "support"}; "state" is `KNOWN` or "not known: <why>". {} when nothing was resolved. Never raises."""
    from app.analysis.development_only import development_only
    from app.analysis.resolved_packages import resolved_in
    from app.tools import osv
    from app.tools.public_data import NotKnown

    root, directory = Path(root), Path(directory)
    try:
        resolved = [r for r in resolved_in(directory, root) if r.ecosystem in osv.ECOSYSTEM]
    except Exception:  # noqa: BLE001
        resolved = []
    if not resolved:
        return {}
    development = development_only(directory)
    out: dict[str, Any] = {"digest": _digest(resolved), "checked": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "found": [], "support": []}
    try:
        found = osv.advisories([osv.Release(r.ecosystem, r.name, r.version) for r in resolved], root)
        by_release = {(r.ecosystem, r.name, r.version): r for r in resolved}
        for release, items in found.items():
            entry = by_release.get((release.ecosystem, release.name, release.version))
            for advisory in items:
                out["found"].append({
                    "ecosystem": release.ecosystem, "package": release.name, "version": release.version,
                    "direct": bool(entry.direct) if entry else False,
                    "development": development.holds(release.ecosystem, release.name), **advisory.as_dict()})
        out["state"] = KNOWN
    except NotKnown as why:
        out["state"] = f"not known: {why}"
    except Exception as error:  # noqa: BLE001
        out["state"] = f"not known: the check failed ({type(error).__name__})"
    out["support"] = _support(root, resolved, development)
    return out


def _support(root: Path, resolved: list[Any], development: Any) -> list[dict[str, Any]]:
    """The support cycle of each runtime the resolved packages run on, and of each direct dependency that ships and
    endoflife.date tracks. A product that cannot be read is left out."""
    from app.stacks import stack_facts
    from app.tools import support_dates
    from app.tools.public_data import NotKnown
    from app.tools.release_fit import numbers

    entries: list[dict[str, Any]] = []
    try:
        banners = stack_facts.toolchains(sorted({r.ecosystem for r in resolved}), root)
    except Exception:  # noqa: BLE001
        banners = {}
    try:
        for ecosystem, banner in banners.items():
            product = support_dates.product_named(support_dates.RUNTIME.get(ecosystem, ""))
            version = ".".join(map(str, numbers(banner)))
            entry = support_dates.support(product, version) if product and version else {}
            if entry:
                entries.append({**entry, "kind": "runtime"})
        for r in [r for r in resolved if r.direct and not development.holds(r.ecosystem, r.name)]:
            product = support_dates.product_of_package(r.ecosystem, r.name)
            entry = support_dates.support(product, r.version) if product else {}
            if entry:
                entries.append({**entry, "kind": "framework", "package": r.name})
    except NotKnown as why:
        logger.info("Support dates not known: %s", why)
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the support dates", exc_info=True)
    return entries


def after_resolving(root: str | Path, directory: str | Path) -> dict[str, Any]:
    """Check what an install in `directory` resolved and keep it in the stack facts; the folder's findings ({} when
    the facts are off, nothing was resolved, or the same set was checked already). Never raises."""
    from app.stacks import stack_facts

    if not stack_facts.enabled():
        return {}
    try:
        root, directory = Path(root), Path(directory)
        where = _where(root, directory)
        before = (stack_facts.read(root).get("advisories") or {}).get(where) or {}
        from app.analysis.resolved_packages import resolved_in

        resolved = resolved_in(directory, root)
        if resolved and before.get("state") == KNOWN and before.get("digest") == _digest(
                [r for r in resolved if r.ecosystem in _ecosystems()]):
            return {}
        found = check(root, directory)
        if not found:
            return {}

        def change(sheet: dict[str, Any]) -> dict[str, Any]:
            advisories = dict(sheet.get("advisories") or {})
            advisories[where] = {k: v for k, v in found.items() if k != "support"}
            # A folder's support entries are its latest install's: a framework upgraded leaves no stale cycle behind.
            support = {k: v for k, v in (sheet.get("support") or {}).items()
                       if not (isinstance(v, dict) and v.get("where") == where)}
            for entry in found.get("support") or []:
                support[f"{entry.get('product')} {entry.get('cycle')}"] = {**entry, "where": where}
            return {**sheet, "advisories": advisories, "support": support}

        stack_facts.amend(root, change)
        return found
    except Exception:  # noqa: BLE001 - the install's result as it was
        logger.debug("Could not check the advisories after an install", exc_info=True)
        return {}


def _ecosystems() -> set[str]:
    from app.tools.osv import ECOSYSTEM

    return set(ECOSYSTEM)


# --- what each reader is told -------------------------------------------------------------------------------------

def _by_package(root: str | Path | None) -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    """(folder, the package's release, its advisories) for each release with any, from the sheet."""
    from app.stacks import stack_facts

    out: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    for where, checked in (stack_facts.read(root).get("advisories") or {}).items():
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for item in (checked or {}).get("found") or []:
            if isinstance(item, dict):
                grouped.setdefault((item.get("ecosystem"), item.get("package"), item.get("version")), []).append(item)
        for items in grouped.values():
            out.append((where, items[0], items))
    return out


def _fix_of(release: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """The release that fixes every advisory named, and whether it is a bump or an upgrade."""
    from app.tools.osv import same_major
    from app.tools.release_fit import numbers

    fixes = [str(i.get("fixed")) for i in items if i.get("fixed")]
    if not fixes:
        return "no fixed release is named yet: replace it, or keep it only with the risk stated"
    fixed = max(fixes, key=lambda v: numbers(v.lstrip("vV")))
    if any(not i.get("fixed") for i in items):
        return f"{fixed} fixes some of them; the rest name no fixed release yet"
    if same_major(str(release.get("version")), fixed):
        return f"fixed in {fixed}, in the same major line: bump to it"
    return f"fixed in {fixed}, a new major line: upgrade with care, not as a plain bump"


def _named(items: list[dict[str, Any]]) -> str:
    from app.tools.osv import rank

    parts = []
    for item in sorted(items, key=lambda i: -rank(i.get("severity")))[:4]:
        severity = str(item.get("severity") or "severity not stated").lower()
        summary = f": {item['summary']}" if item.get("summary") else ""
        parts.append(f"{item.get('id')} ({severity}){summary}")
    more = len(items) - 4
    return "; ".join(parts) + (f"; and {more} more" if more > 0 else "")


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _at_the_bar(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in items if str(i.get("severity") or "").upper() in BAR]


def release_gaps(root: str | Path | None) -> list[str]:
    """What the release ships against the advisories and support dates kept: [] when off or nothing was found."""
    from app.stacks import stack_facts

    if not stack_facts.enabled() or not root:
        return []
    gaps: list[str] = []
    for where, release, items in _by_package(root):
        serious = _at_the_bar(items)
        if not serious:
            continue
        head = DEVELOPMENT_ADVISORY if release.get("development") else ADVISORY_GAP
        gaps.append(f"{head} `{release.get('package')}` {release.get('version')} ({release.get('ecosystem')}, in "
                    f"`{where}`) - {_named(serious)}. {_sentence(_fix_of(release, serious))}.")
    sheet = stack_facts.read(root)
    for entry in (sheet.get("support") or {}).values():
        if isinstance(entry, dict) and entry.get("ended"):
            from app.tools.support_dates import described

            gaps.append(f"{PAST_SUPPORT} {described(entry)} ({entry.get('kind')}, in `{entry.get('where')}`).")
    for where, checked in (sheet.get("advisories") or {}).items():
        state = str((checked or {}).get("state") or "")
        if state and state != KNOWN:
            gaps.append(f"{NOT_KNOWN} {state.removeprefix('not known: ')} (in `{where}`).")
    return gaps


def for_the_security_reviewer(root: str | Path | None) -> str:
    """The advisories and support dates kept, as a short section of evidence; "" when off or there are none."""
    from app.stacks import stack_facts
    from app.tools.support_dates import described

    if not stack_facts.enabled() or not root:
        return ""
    sheet = stack_facts.read(root)
    lines: list[str] = []
    for where, release, items in sorted(_by_package(root), key=lambda x: (bool(x[1].get("development")),
                                                                          not _at_the_bar(x[2]))):
        label = "development only, does not ship" if release.get("development") else "ships"
        lines.append(f"- {label}: `{release.get('package')}` {release.get('version')} ({release.get('ecosystem')}, "
                     f"in `{where}`) - {_named(items)}; {_fix_of(release, items)}.")
    shown = lines[:MOST_LINES] + ([f"- and {len(lines) - MOST_LINES} more"] if len(lines) > MOST_LINES else [])
    support = [f"- {described(e)} ({e.get('kind')})" for e in (sheet.get("support") or {}).values()
               if isinstance(e, dict)]
    unknown = [f"- in `{w}`: {c.get('state')}" for w, c in (sheet.get("advisories") or {}).items()
               if isinstance(c, dict) and c.get("state") and c.get("state") != KNOWN]
    if not shown and not support and not unknown:
        return ""
    checked = [w for w, c in (sheet.get("advisories") or {}).items() if isinstance(c, dict) and c.get("state") == KNOWN]
    parts = [f"\n{HEADING}\n"
             "Read by the harness from OSV and endoflife.date for the exact releases the install resolved. A "
             "dependency that ships with an advisory of high or critical severity is a finding: its remediation is "
             "the fixed release named - a bump within the same major line, and across a major line an upgrade to "
             "make with care. A package for development only does not ship and is never a blocking finding."]
    if shown:
        parts.append("Advisories:\n" + "\n".join(shown))
    elif checked:
        parts.append("Advisories: none known for the releases resolved in " + ", ".join(f"`{w}`" for w in checked) + ".")
    if support:
        parts.append("Support windows:\n" + "\n".join(support[:MOST_LINES]))
    if unknown:
        parts.append("Not known (the source could not be read - not the same as none):\n" + "\n".join(unknown))
    return "\n".join(parts) + "\n"


__all__ = ["ADVISORY_GAP", "BAR", "DEVELOPMENT_ADVISORY", "HEADING", "NOT_KNOWN", "PAST_SUPPORT", "after_resolving",
           "check", "for_the_security_reviewer", "release_gaps"]
