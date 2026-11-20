"""A dependency manifest is written with the registry's current releases in front of it (plan WL.4, T4).

The registry's real versions reached a fixer only after an install had failed on a version that does not exist
(`contract._the_versions_that_exist`, LF.1132 and LF.1138). Measured on one Ruby run, a Gemfile pinned a version
RubyGems never had and the product did not install for 267 minutes. Here the registry is asked before the manifest is
drafted. Each package the specification names, in its library calls and its configuration, is looked up in the
manifest's own registry (`package_registry.look_up`). The ones it has are shown to the drafting request under
`HEADING`.

Only package registries are asked, never a search: they are package metadata, which every run reads to install at
all. So this follows `PACKAGE_LOOKUP_ENABLED`, not the run's "Internet lookups" choice (`app.internet_lookups`). It is
built in (a fix for invented versions, `switches.BUILT_IN`); its variable set off is a test's hook.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; built in, so on in the product.
ON_BY_DEFAULT = False
SWITCH = "REGISTRY_VERSIONS_BEFORE_A_MANIFEST"
#: Packages asked about for one manifest.
MOST_PACKAGES = 12
#: Registry requests made at once.
AT_ONCE = 6

HEADING = "--- Current releases from the registry ---"
NOTE = ("The {registry} registry's current release of each package the specification names, asked just now. Pin each "
        "at the release shown, or at the version the specification names where that release line exists; never at a "
        "version newer than the one shown, which the registry does not have.")

#: The section already shown for (workspace, manifest): one lookup and one ledger record per manifest per run.
_SHOWN: dict[tuple[str, str], str] = {}

_A_NAME = r"@?[A-Za-z][\w.\-]*(?:[/:][\w.\-]+)*"
#: A name with its version attached (`fastapi==0.115.0`, `serde@1.0`, `left-pad^1.3`), or quoted before one
#: (`` `hono` 4.6 ``).
_A_NAME_AND_VERSION = re.compile(rf"(?<![\w@./:-])({_A_NAME})(?:@|==|~=|>=|\^|~)v?\d+(?:\.\d+)*"
                                 rf"|`({_A_NAME})`\s+v?\d+\.\d+")
#: In an entry about a dependency, a name and a version apart: `dependency: hono 4.6.14`, `gin v1.10`.
_A_NAME_THEN_A_VERSION = re.compile(rf"(?<![\w@./:-])({_A_NAME})\s+v?\d+\.\d+")
_ABOUT_A_DEPENDENCY = re.compile(r"\b(?:dependenc\w*|package\w*|librar\w*)\b", re.I)
#: The name an entry opens with: `hono - new Hono()`, `**fastapi** (0.115): ...`.
_THE_FIRST_NAME = re.compile(rf"^[\s*_`\"'-]*({_A_NAME})")
#: Words an entry may open with or put before a version that name no package.
_NOT_A_PACKAGE = frozenset({"a", "an", "the", "it", "uses", "use", "using", "with", "version", "v", "library",
                            "framework", "package", "dependency", "dependencies", "import", "from", "call", "calls",
                            "built", "against", "at", "on", "is"})


def enabled() -> bool:
    from app.tools import package_registry

    return is_on(SWITCH, ON_BY_DEFAULT) and package_registry.enabled()


def is_a_dependency_manifest(path: str) -> bool:
    """Whether `path` is a file that declares packages, by the harness's own table of them."""
    from app.stacks.contract import _NESTED_MANIFESTS
    from app.tools.repository import PACKAGE_MANIFESTS

    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name in PACKAGE_MANIFESTS or any(fnmatch.fnmatchcase(name, glob) for glob in _NESTED_MANIFESTS)


def registry_of(path: str, stack: Any = None) -> str | None:
    """The registry a manifest's packages come from: by the dependency gate's table of manifests, else by the language
    table's language whose manifest it is, else by the stack's language; None for none."""
    from app.stacks.languages import LANGUAGES
    from app.tools import dependency_gate, package_registry

    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1]
    for registry in dependency_gate.REGISTRIES.values():
        if name in registry.manifests:
            return registry.ecosystem
    for row in LANGUAGES:
        if any(fnmatch.fnmatchcase(name, glob) for glob in row.manifests):
            found = package_registry.ecosystem_named(row.name)
            if found:
                return found
    return package_registry.ecosystem_named(str(getattr(stack, "language", "") or ""))


def named_packages(specification: Any) -> list[str]:
    """The packages the specification names, in the order it names them: the library each library-call entry opens
    with, and each name given a version in it or in the configuration. Runtimes (`node 22`) are not packages."""
    from app.tools import package_registry

    names: list[str] = []
    calls = [str(entry) for entry in getattr(specification, "library_usage", None) or []]
    for entry in calls:
        first = _THE_FIRST_NAME.match(entry)
        if first:
            names.append(first.group(1))
    for entry in [*calls, *(str(e) for e in getattr(specification, "configuration", None) or [])]:
        names.extend(match.group(1) or match.group(2) for match in _A_NAME_AND_VERSION.finditer(entry))
        if _ABOUT_A_DEPENDENCY.search(entry):
            names.extend(match.group(1) for match in _A_NAME_THEN_A_VERSION.finditer(entry))
    kept: list[str] = []
    for name in names:
        name = name.rstrip(".:-")
        if (len(name) < 2 or name.lower() in _NOT_A_PACKAGE or package_registry.ecosystem_named(name)
                or name.lower() in {k.lower() for k in kept}):
            continue
        kept.append(name)
    return kept[:MOST_PACKAGES]


def section(root: str | Path, path: str, specification: Any, stack: Any = None) -> str:
    """The registry's current release of each package the specification names, for a request drafting the dependency
    manifest `path`; "" when off, not a dependency manifest, or when the registry has none of them. Never raises."""
    try:
        if not enabled() or specification is None or not is_a_dependency_manifest(path):
            return ""
        key = (str(root), str(path))
        if key in _SHOWN:
            return _SHOWN[key]
        registry = registry_of(path, stack)
        names = named_packages(specification)
        if not registry or not names:
            return ""
        from app.tools import package_registry

        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            answers = list(pool.map(lambda name: package_registry.look_up(registry, name), names))
        lines = []
        for name, answer in zip(names, answers):
            if answer.get("error") or not answer.get("version"):
                continue
            note = f" ({answer['note']})" if answer.get("note") else ""
            lines.append(f"- `{answer.get('package') or name}`: {answer['version']}{note}")
        shown = "\n".join([HEADING, NOTE.format(registry=registry), *lines]) if lines else ""
        _SHOWN[key] = shown
        try:
            from app.observability import defect_ledger

            defect_ledger.note("lookup", "drafting", detail=(
                f"T4 registry versions before drafting `{path}`: {len(names)} asked of {registry}, {len(lines)} found"))
        except Exception:  # noqa: BLE001 - a record must never fail the draft
            pass
        return shown
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not look up the registry's releases for %s", path, exc_info=True)
        return ""


__all__ = ["HEADING", "NOTE", "ON_BY_DEFAULT", "SWITCH", "enabled", "is_a_dependency_manifest", "named_packages",
           "registry_of", "section"]
