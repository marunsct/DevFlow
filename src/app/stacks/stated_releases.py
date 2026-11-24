"""The release line a brief asks for wins over a stack pack's pinned version (LF.1311; plan HK.1's rule, held by packs).

Found while building the stale-knowledge benchmark family: its brief reads "Java 21, on Spring Boot 4.2 (the current
release line; not 3.x)", and the Java pack's scaffold wrote its own pin, Spring Boot 3.4.5, whatever the brief said -
as the NestJS pack wrote `^11` with 12 released. HK.1's rule ("the brief's stated version always wins") was held by the
stack facts and not by the packs, and the scaffold is where a run's versions are first written.

So a pack declares the frameworks it pins as release families (`StackPack.release_families`): how a brief names each,
the registry package leading its line, where each pin is written, and what its files say differently on another line.
At the scaffold:

1. a release the brief states next to a family's name ("Spring Boot 4.2", "NestJS 12", "spring-boot v4") is read from
   its constraints first, then from the rest of it; a line it rules out ("not 3.x") is not one it asks for;
2. the line's newest stable release this toolchain runs is read from the registry (`release_fit.newest_on_line`), and
   every other package the family keeps in step is written at its own newest release on that line - never a guess:
   a line the registry does not list, or a registry that cannot be read, keeps the pack's pin and says so;
3. a line the toolchain cannot run (each release needs a newer runtime than the one here) keeps the pack's pin and is
   named at once as a stated cause, in the stack facts' mismatches the first defect and the release read (HK.2);
4. a setup on the asked line that fails its own smoke test is set up again on the pack's pin, and that is said too;
5. the choice is kept in the stack facts (`stated_releases`: "the brief asked for 4.2; pinned 4.2.0") and every fixer
   is told it, and the contract records the versions written, so every later reading of the scaffold renders them.

A brief that names no family's release leaves the pack exactly as it is: the known-good pin, no registry read.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from app.stacks import ReleaseFamily, StackPack

logger = logging.getLogger(__name__)

#: Where the stack facts keep the choices, and the key their mismatches are kept under.
FACTS_KEY = "stated_releases"
MISMATCH_KEY = "the brief's release line"
#: How a fixer is told the releases the brief asked for (`stack_facts.for_a_fixer`).
FIXER_LINE = "Releases the brief asks for:"

#: Words just before a name that make what follows a line the brief rules out, not one it asks for.
_RULED_OUT = re.compile(r"\b(?:not|no|never|avoid|without|instead\s+of|rather\s+than|except|unlike|from)\s*$", re.I)
#: A version written straight after a name: `4.2`, `v12`, `version 4`, `@12`, `3.x`.
_A_LINE = r"\s*(?:,\s*)?(?:v(?:ersion)?\.?\s*|@)?(?P<line>\d{1,3}(?:\.\d{1,4}){0,2})(?:\.[xX*])?(?![\w.]*\d)"


@dataclass(frozen=True)
class Choice:
    """What the scaffold writes for the brief's releases: the pack to scaffold and what is said about it."""

    #: The pack to scaffold: `base` with the asked releases written, or `base` itself.
    pack: StackPack
    #: The pack as declared.
    base: StackPack
    #: One entry per family the brief asked a release of: title, package, asked, pinned, the pack's pin, why.
    facts: tuple[dict[str, Any], ...] = ()
    #: Lines the toolchain cannot run, as the stack facts keep a mismatch (`toolchain_fit`).
    mismatches: tuple[dict[str, Any], ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.pack.releases)

    @property
    def said(self) -> str:
        """The choices in one sentence each, for the scaffold's decision record; "" when the brief asked for none."""
        return " ".join(f"{str(entry['why'])[0].upper()}{str(entry['why'])[1:]}." for entry in self.facts)


def _name_pattern(name: str) -> str:
    return r"[\s-]*".join(re.escape(part) for part in re.split(r"[\s-]+", name.strip()) if part)


def asked_line(document_text: str, family: ReleaseFamily) -> tuple[int, ...]:
    """The release line the brief asks for of `family`, as its leading numbers ((4, 2) for "Spring Boot 4.2"); () when
    it names none. The brief's technical constraints are read first, then the rest of it."""
    from app.agents.brief_constraints import constraint_lines

    names = sorted((n for n in family.names if n.strip()), key=len, reverse=True)
    if not names or not document_text:
        return ()
    pattern = re.compile(r"(?<![\w@/.-])(?:" + "|".join(_name_pattern(n) for n in names) + r")(?![\w-])" + _A_LINE,
                         re.I)
    for text in ("\n".join(constraint_lines(document_text)), document_text):
        for found in pattern.finditer(text):
            if _RULED_OUT.search(text[max(0, found.start() - 24):found.start()]):
                continue
            return tuple(int(part) for part in found.group("line").split("."))
    return ()


def _line_words(line: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in line)


def pinned_in(files: Mapping[str, str], family: ReleaseFamily, package: str) -> str:
    """The version `files` hold for `package` at its first place in `family`; "" when no place matches."""
    for named, path, pattern in family.places:
        if named != package:
            continue
        found = re.search(pattern, str(files.get(path) or ""))
        if found:
            return found.group("version")
    return ""


def _the_line_s_variant(family: ReleaseFamily, version: str):
    from app.tools.release_fit import numbers

    parts = numbers(version)
    matching = [key for key in family.lines if numbers(key) and parts[: len(numbers(key))] == numbers(key)]
    return family.lines[max(matching, key=lambda key: len(numbers(key)))] if matching else None


def _written(files: Mapping[str, str], family: ReleaseFamily, versions: Mapping[str, str]) -> dict[str, str]:
    out = dict(files)
    for package, path, pattern in family.places:
        version = versions.get(package)
        if not version or path not in out:
            continue
        out[path] = re.sub(pattern, lambda m: m.group(0)[: m.start("version") - m.start(0)] + version
                           + m.group(0)[m.end("version") - m.start(0):], out[path])
    return out


def applied(pack: StackPack, versions: Mapping[str, str] | None) -> StackPack:
    """`pack` with `versions` (by package) written at each family's places, and the files, smoke tests, golden
    example and known errors its families declare for the line of the version written. `pack` itself when none."""
    versions = {str(k): str(v) for k, v in (versions or {}).items() if v}
    if not versions or not pack.release_families:
        return pack
    files, smoke, golden, known = dict(pack.files), dict(pack.smoke_files), dict(pack.golden_example), dict(pack.known_errors)
    for family in pack.release_families:
        leader = versions.get(family.package)
        variant = _the_line_s_variant(family, leader) if leader else None
        if variant is not None:
            files.update(variant.files)
            smoke.update(variant.smoke_files)
            golden.update(variant.golden_example)
            known.update(variant.known_errors)
        files = _written(files, family, versions)
        smoke = _written(smoke, family, versions)
    return dataclasses.replace(pack, files=files, smoke_files=smoke, golden_example=golden, known_errors=known,
                               releases=dict(versions))


def _registry_readable() -> bool:
    from app.tools import package_registry

    return package_registry.enabled()


def _for_a_family(pack: StackPack, family: ReleaseFamily, line: tuple[int, ...], root: str | Path | None,
                  fetch: Any) -> tuple[dict[str, str], dict[str, Any], dict[str, Any] | None]:
    """(versions to write, the fact, a mismatch or None) for one family the brief asked `line` of."""
    from app.tools import release_fit

    default = pinned_in(pack.files, family, family.package)
    asked = _line_words(line)
    fact: dict[str, Any] = {"framework": family.title, "package": family.package, "asked": asked,
                            "pack_pin": default}
    if default and release_fit.on_the_line(default, line):
        return {}, {**fact, "pinned": default,
                    "why": f"the brief asked for {family.title} {asked}; the pack's {default} is on that line"}, None
    keeps = f"so the pack's {default} is kept" if default else "so the pack's own pin is kept"
    if not _registry_readable():
        return {}, {**fact, "pinned": default,
                    "why": f"the brief asked for {family.title} {asked}; registry lookups are off here, {keeps}"}, None
    here = release_fit.toolchain(family.ecosystem, root)
    found = release_fit.newest_on_line(family.ecosystem, family.package, line, here, fetch=fetch)
    if not found:
        return {}, {**fact, "pinned": default, "why": f"the brief asked for {family.title} {asked}; the "
                    f"{family.ecosystem} registry could not be read, {keeps}"}, None
    if not found.get("newest"):
        return {}, {**fact, "pinned": default, "why": f"the brief asked for {family.title} {asked}; the "
                    f"{family.ecosystem} registry lists no stable {asked} release (its newest is "
                    f"{found.get('latest') or 'unknown'}), {keeps}"}, None
    runtime = release_fit.RUNTIME_OF.get(family.ecosystem, family.ecosystem)
    if not found.get("version"):
        needs = f"{runtime} {found.get('needs') or 'a newer runtime'}"
        why = (f"the brief asked for {family.title} {asked}; its newest release, {found['newest']}, needs {needs} and "
               f"this environment has {here}, {keeps} - the product cannot be built on the line asked for here")
        mismatch = {"ecosystem": family.ecosystem, "package": family.package, "version": found["newest"],
                    "needs": needs, "toolchain": here, "source": "the release line the brief asks for",
                    "direct": True, "said": f"The brief asks for {family.title} {asked}: {why}."}
        return {}, {**fact, "pinned": default, "why": why}, mismatch
    versions = {family.package: found["version"]}
    for member in dict.fromkeys(p for p, _f, _p in family.places if p != family.package):
        kept = release_fit.newest_on_line(family.ecosystem, member, line, here, fetch=fetch)
        if not kept.get("version"):
            return {}, {**fact, "pinned": default, "why": f"the brief asked for {family.title} {asked}; {member}, "
                        f"which the pack keeps in step with it, has no {asked} release this toolchain runs, {keeps}"}, None
        versions[member] = kept["version"]
    why = (f"the brief asked for {family.title} {asked}; pinned {found['version']}, the newest {asked} release this "
           f"toolchain runs" + (f" ({runtime} {found['needs']})" if found.get("needs") else ""))
    if len(versions) > 1:
        why += ", with " + ", ".join(f"{p} {v}" for p, v in versions.items() if p != family.package) + " in step"
    return versions, {**fact, "pinned": found["version"], "released": found.get("released") or "", "why": why}, None


def on_line(pack: StackPack, family: ReleaseFamily, line: tuple[int, ...], root: str | Path | None = None, *,
            fetch: Any = None) -> Choice:
    """The choice for `family` asked at `line`, as a brief asking for it would get (the pack check reads it)."""
    versions, fact, mismatch = _for_a_family(pack, family, line, root, fetch)
    return Choice(pack=applied(pack, versions), base=pack, facts=(fact,), mismatches=(mismatch,) if mismatch else ())


def choose(pack: StackPack | None, document_text: str, root: str | Path | None = None, *, fetch: Any = None) -> Choice | None:
    """The pack to scaffold for this brief: each release line it asks for written in, with what is said about it; the
    pack as it is when the brief asks for none. None for no pack. Never raises: the pack as it is."""
    if pack is None:
        return None
    try:
        versions: dict[str, str] = {}
        facts: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        for family in pack.release_families:
            line = asked_line(document_text, family)
            if not line:
                continue
            chosen, fact, mismatch = _for_a_family(pack, family, line, root, fetch)
            versions.update(chosen)
            facts.append(fact)
            if mismatch:
                mismatches.append(mismatch)
        return Choice(pack=applied(pack, versions), base=pack, facts=tuple(facts), mismatches=tuple(mismatches))
    except Exception:  # noqa: BLE001 - the pack's known-good pins
        logger.warning("Could not read the releases the brief asks for", exc_info=True)
        return Choice(pack=pack, base=pack)


def fall_back(repo_root: str | Path, project: str, title: str, package: str | None, choice: Choice,
              problem: str) -> Choice:
    """After a setup on the asked releases failed its own smoke test: the files it wrote that the pack's own pins write
    differently, and its lock files, removed so the next scaffold writes the pack's; the choice on the pack's pins,
    saying why. Never raises."""
    base = choice.base
    try:
        from app.stacks.languages import LOCKFILES

        folder = Path(repo_root) / project
        asked = choice.pack.render(project, title, package)
        own = base.render(project, title, package)
        for relative, text in asked.items():
            target = folder / relative
            if own.get(relative) != text and target.is_file() and target.read_text(encoding="utf-8") == text:
                target.unlink()
        for name in LOCKFILES:
            (folder / name).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - the next scaffold writes what is missing
        logger.debug("Could not clear the setup on the asked releases", exc_info=True)
    said = " ".join(str(problem or "").split())[:300]
    facts = []
    for entry in choice.facts:
        if entry.get("pinned") and entry.get("pinned") != entry.get("pack_pin"):
            entry = {**entry, "pinned": entry.get("pack_pin") or "", "why": (
                f"the brief asked for {entry['framework']} {entry['asked']}; the setup on {entry['pinned']} did not pass "
                f"its own smoke test ({said or 'no reason given'}), so it was set up on the pack's "
                f"{entry.get('pack_pin') or 'own pin'} - the product is not on the line asked for")}
        facts.append(entry)
    return Choice(pack=base, base=base, facts=tuple(facts), mismatches=choice.mismatches)


def record(repo_root: str | Path, choice: Choice | None) -> None:
    """Keep the choice in the stack facts: what was asked and pinned, and a line the toolchain cannot run as a
    mismatch. Nothing when the brief asked for no release. Never raises."""
    if choice is None or not choice.facts:
        return
    from app.stacks import stack_facts

    def change(sheet: dict[str, Any]) -> dict[str, Any]:
        mismatches = dict(sheet.get("mismatches") or {}) if isinstance(sheet.get("mismatches"), dict) else {}
        if choice.mismatches:
            mismatches[MISMATCH_KEY] = [dict(m) for m in choice.mismatches]
        else:
            mismatches.pop(MISMATCH_KEY, None)
        return {**sheet, FACTS_KEY: [dict(f) for f in choice.facts], "mismatches": mismatches}

    stack_facts.amend(repo_root, change)


def for_a_fixer(sheet: Mapping[str, Any]) -> str:
    """One line naming each release the brief asked for and what is pinned, and why; "" when it asked for none."""
    entries = [e for e in sheet.get(FACTS_KEY) or [] if isinstance(e, dict) and e.get("asked") and e.get("why")]
    if not entries:
        return ""
    from app.tools.release_fit import numbers, on_the_line

    kept = any(on_the_line(str(e.get("pinned") or ""), numbers(e.get("asked"))) for e in entries)
    return (f"{FIXER_LINE} " + "; ".join(str(e["why"]) for e in entries) + "."
            + (" Keep each pin on the line asked for: an older line does not meet the brief." if kept else ""))


__all__ = ["Choice", "FACTS_KEY", "FIXER_LINE", "MISMATCH_KEY", "applied", "asked_line", "choose", "fall_back",
           "for_a_fixer", "on_line", "pinned_in", "record"]
