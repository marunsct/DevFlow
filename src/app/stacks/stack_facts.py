"""One standing sheet of what is true today about the project's toolchain and dependencies (HK.1, LF.1292).

A person choosing or pinning a library checks what is current and whether it fits their toolchain; a model writes the
versions it was trained on. Measured: Rust runs never built on crates needing a newer rustc than the image's; a C# run
restored a package for a newer .NET every round (NU1202); a Ruby run pinned a gem version RubyGems never had. Each
stage that asked the registry did so on its own, and nothing kept the answer for the next stage.

So the harness keeps `.harness/stack-facts.json`: the toolchain versions here; for each dependency the release chosen
and why (the newest stable release this toolchain runs, `app.tools.release_fit`), the registry's newest, its release
date, whether it was withdrawn (yanked, deprecated, unlisted, abandoned), the runtime it needs and the version the
project resolved; and the toolchain mismatches the fit check found after an install (`app.stacks.toolchain_fit`). It
is written when the architect's reading is done and after each install resolves, and read by:

- the stack selector: the toolchains this environment runs (`toolchains_section`);
- the architect: each library's chosen release, date and withdrawal (`library_lines`);
- the drafting of a manifest: the toolchain beside the registry's releases (`app.graph.registry_versions`);
- every fixer: the toolchain and the versions resolved, in two lines (`for_a_fixer`);
- release: a withdrawn dependency or an unresolved mismatch shipped, as a gap (`release_gaps`).

A version the brief or the project pins is never changed here: the sheet records it beside the newest that fits.
Only public package names leave, to their own registry, as for every registry read (`package_registry`). Built in (a
fix): `STACK_FACTS` set off is a test's hook, so no test reaches a registry.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SWITCH = "STACK_FACTS"
#: Off in code like every built-in fix; on in the product (`switches.BUILT_IN`).
ON_BY_DEFAULT = False
#: Where the sheet is kept, from the workspace root.
SHEET = ".harness/stack-facts.json"
#: Dependencies described in one sheet.
MOST_DEPENDENCIES = 30
#: Registry reads at once.
AT_ONCE = 8
#: Folders searched for a project's manifests below the workspace root.
DEPTH = 3

TOOLCHAINS_HEADING = "--- The toolchains this environment runs ---"
VERSIONS_LINE = "Versions here:"
TOOLCHAIN_LINE = "Toolchain here:"
#: How the release names what it ships against the facts: notes, not blocking (`app.completion_verdict`) - a suite
#: that passed at release ran on what was resolved.
WITHDRAWN_GAP = "A dependency its registry marks withdrawn ships:"
MISFIT_GAP = "A resolved package needs a newer toolchain than the one here:"

_WRITING = threading.Lock()


def enabled() -> bool:
    from app.switches import is_on
    from app.tools import package_registry

    return is_on(SWITCH, ON_BY_DEFAULT) and package_registry.enabled()


def read(root: str | Path | None) -> dict[str, Any]:
    """The sheet as kept; {} when there is none."""
    if not root:
        return {}
    try:
        data = json.loads((Path(root) / SHEET).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(root: str | Path, sheet: dict[str, Any]) -> None:
    path = Path(root) / SHEET
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sheet, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _installed(banner: str) -> bool:
    from app.tools.release_fit import numbers

    return bool(banner) and banner != "not installed" and bool(numbers(banner))


def toolchains(ecosystems: Iterable[str] | None = None, root: str | Path | None = None) -> dict[str, str]:
    """{ecosystem: its toolchain's version banner} for each installed here (all registries' when none are named)."""
    from app.tools import package_registry, release_fit

    names = list(ecosystems) if ecosystems is not None else list(package_registry._ECOSYSTEMS)  # noqa: SLF001
    found = {}
    for ecosystem in dict.fromkeys(names):
        try:
            banner = release_fit.toolchain(ecosystem, root)
        except Exception:  # noqa: BLE001 - unknown is not installed
            continue
        if _installed(banner):
            found[ecosystem] = banner
    return found


def _toolchain_words(toolchain: dict[str, str]) -> str:
    """`node 24.11.1; rustc 1.85.1`: each toolchain by its runtime's name and version."""
    from app.tools.release_fit import RUNTIME_OF, numbers

    return "; ".join(f"{RUNTIME_OF.get(e, e)} {'.'.join(map(str, numbers(banner)))}"
                     for e, banner in toolchain.items() if numbers(banner))


def toolchains_section() -> str:
    """For the stack selector: each toolchain this environment runs, with what it means for a choice. "" when off."""
    if not enabled():
        return ""
    try:
        found = toolchains()
    except Exception:  # noqa: BLE001 - the request as it was
        return ""
    if not found:
        return ""
    return (f"{TOOLCHAINS_HEADING}\n" + "\n".join(f"- {_toolchain_words({e: b})} ({e} packages)" for e, b in found.items())
            + "\nA library whose current release needs a newer runtime than these is installed at an older release "
              "that fits, or not at all: prefer one whose current release runs here.\n\n")


# --- what is declared, and each dependency's facts ----------------------------------------------------------------

def _project_directories(root: Path) -> list[Path]:
    """The folders at most `DEPTH` below the workspace holding a manifest of some language, nearest first; hidden
    folders, installed packages and build output are not entered."""
    import fnmatch

    from app.stacks.languages import MANIFESTS, NOT_THE_PRODUCT, is_generated

    found: list[Path] = []
    level = [root]
    for _ in range(DEPTH + 1):
        below: list[Path] = []
        for directory in level:
            try:
                entries = list(directory.iterdir())
            except OSError:
                continue
            names = [e.name for e in entries if e.is_file()]
            if any(fnmatch.fnmatchcase(name, glob) for name in names for glob in MANIFESTS):
                found.append(directory)
            below.extend(sorted(e for e in entries if e.is_dir() and not e.is_symlink() and not e.name.startswith(".")
                                and e.name not in NOT_THE_PRODUCT and not is_generated(e.name, names)))
        level = below
    return found


def _declared(directory: Path) -> list[tuple[str, str]]:
    """(ecosystem, package) for each package the manifests in `directory` declare, by the dependency gate's readers."""
    from app.tools.dependency_gate import REGISTRIES

    out: list[tuple[str, str]] = []
    for registry in REGISTRIES.values():
        if registry.declared is None:
            continue
        if registry.manifests and not any((directory / name).is_file() for name in registry.manifests):
            if not (registry.ecosystem == "nuget" and any(directory.glob("*.csproj"))):
                continue
        try:
            out.extend((registry.ecosystem, name) for name in registry.declared(directory))
        except Exception:  # noqa: BLE001 - an unreadable manifest declares nothing here
            continue
    return out


def fact(ecosystem: str, name: str, root: str | Path | None = None) -> dict[str, Any]:
    """One dependency's facts: the release chosen and why, the registry's newest, its date, whether it was withdrawn,
    the runtime it needs; {} when the registry has no such package or cannot be read. Never raises."""
    from app.tools import package_registry, release_fit

    try:
        answer = package_registry.look_up(ecosystem, name)
        if answer.get("error") or not answer.get("version"):
            return {}
        version = str(answer["version"])
        chosen = release_fit.needs_of(ecosystem, str(answer.get("package") or name), version)
        stated = answer.get("needs_runtime") if isinstance(answer.get("needs_runtime"), dict) else {}
        entry = {
            "ecosystem": ecosystem,
            "package": str(answer.get("package") or name),
            "version": version,
            "newest": str(answer.get("newest_release") or version),
            "why": str(answer.get("note") or "the newest stable release; it fits this toolchain"),
            "released": chosen.released,
            "needs": chosen.needs if chosen.needs else ", ".join(f"{k} {v}" for k, v in stated.items()
                                                                if v not in ("any", "not stated")),
            "withdrawn": chosen.withdrawn or str(answer.get("withdrawn") or ""),
        }
        return {key: value for key, value in entry.items() if value}
    except Exception:  # noqa: BLE001 - no fact rather than a crash
        logger.debug("Could not describe %s %s", ecosystem, name, exc_info=True)
        return {}


def write(root: str | Path, *, stack: Any = None, libraries: Iterable[str] = (), ecosystem: str = "",
          mismatches: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Write the sheet for the workspace at `root` and return it; {} when off. Never raises.

    The dependencies are those the project's manifests declare; before there is a manifest, `libraries` (the stack's,
    in `ecosystem`). `mismatches`: the fit check's findings by the folder they were found in, replacing that folder's.
    """
    if not enabled():
        return {}
    try:
        from app.analysis.resolved_packages import resolved_in
        from app.tools import package_registry

        root = Path(root)
        wanted: list[tuple[str, str, str]] = []
        resolved: dict[tuple[str, str], str] = {}
        for directory in _project_directories(root):
            where = str(directory.relative_to(root)) if directory != root else "."
            wanted.extend((ecosystem_, name, where) for ecosystem_, name in _declared(directory))
            for entry in resolved_in(directory, root):
                if entry.direct:
                    resolved[(entry.ecosystem, entry.name.lower())] = entry.version
        if not wanted:
            found = ecosystem or package_registry.ecosystem_named(str(getattr(stack, "language", "") or "")) or ""
            wanted = [(found, name, "the stack") for name in libraries if found]
        seen: set[tuple[str, str]] = set()
        wanted = [w for w in wanted if not ((w[0], w[1].lower()) in seen or seen.add((w[0], w[1].lower())))]
        wanted = wanted[:MOST_DEPENDENCIES]
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            facts = list(pool.map(lambda w: fact(w[0], w[1], root), wanted))
        dependencies = []
        for (ecosystem_, name, where), entry in zip(wanted, facts):
            if not entry:
                continue
            pinned = resolved.get((ecosystem_, name.lower()))
            if pinned:
                entry["resolved"] = pinned
            dependencies.append({**entry, "declared_in": where})
        with _WRITING:
            sheet = read(root)
            kept = dict(sheet.get("mismatches") or {}) if isinstance(sheet.get("mismatches"), dict) else {}
            kept.update(mismatches or {})
            ecosystems = [d["ecosystem"] for d in dependencies] + [e for e in (ecosystem,) if e]
            sheet = {
                "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "toolchain": toolchains(ecosystems or None, root) if ecosystems else dict(sheet.get("toolchain") or {}),
                "dependencies": dependencies or list(sheet.get("dependencies") or []),
                "mismatches": {k: v for k, v in kept.items() if v},
            }
            _save(root, sheet)
        return sheet
    except Exception:  # noqa: BLE001 - the run goes on without its sheet
        logger.warning("Could not write the stack facts", exc_info=True)
        return {}


# --- what each stage is told --------------------------------------------------------------------------------------

def _describe(entry: dict[str, Any]) -> str:
    parts = [f"{entry.get('package')} {entry.get('version')}"]
    if entry.get("released"):
        parts.append(f"released {entry['released']}")
    if entry.get("needs"):
        parts.append(f"needs {entry['needs']}")
    if entry.get("newest") and entry.get("newest") != entry.get("version"):
        parts.append(f"newest {entry['newest']}, which needs a newer toolchain than this one")
    if entry.get("withdrawn"):
        parts.append(f"WITHDRAWN ({entry['withdrawn']}): choose another release or package")
    return "; ".join(parts)


def library_lines(root: str | Path | None, stack: Any, libraries: Iterable[str]) -> str:
    """For the architect: the sheet written for the stack's libraries, as lines; "" when off or none was found."""
    if not enabled() or not root:
        return ""
    from app.tools import package_registry

    ecosystem = package_registry.ecosystem_named(str(getattr(stack, "language", "") or "")) or ""
    sheet = write(root, stack=stack, libraries=list(libraries), ecosystem=ecosystem)
    entries = [d for d in sheet.get("dependencies") or [] if isinstance(d, dict)]
    if not entries:
        return ""
    toolchain = _toolchain_words(sheet.get("toolchain") or {})
    return ("Stack facts (`.harness/stack-facts.json`): the release of each library this environment's toolchain runs"
            + (f" - {toolchain}" if toolchain else "") + ".\n"
            + "\n".join(f"- {_describe(entry)}" for entry in entries))


def toolchain_line(root: str | Path | None, ecosystem: str) -> str:
    """For a manifest's drafting: the toolchain its packages must run on; "" when off or unknown."""
    if not enabled() or not ecosystem:
        return ""
    found = (read(root).get("toolchain") or {}).get(ecosystem) or toolchains([ecosystem], root).get(ecosystem)
    return f"{TOOLCHAIN_LINE} {_toolchain_words({ecosystem: found})}. A release that needs a newer one does not install here." if found else ""


def for_a_fixer(root: str | Path | None) -> str:
    """Two lines for every fix request: the toolchain here, and the versions the project resolved (each mismatch the
    fit check found first). "" when off or there is no sheet."""
    if not enabled():
        return ""
    sheet = read(root)
    toolchain = _toolchain_words(sheet.get("toolchain") or {})
    mismatches = [m for found in (sheet.get("mismatches") or {}).values() for m in found or [] if isinstance(m, dict)]
    versions = [f"{m.get('package')} {m.get('version')} (needs {m.get('needs')}; does not fit"
                + (f", {m['fits']} fits" if m.get("fits") else "") + ")" for m in mismatches]
    versions += [f"{d.get('package')} {d.get('resolved') or d.get('version')}"
                 + (f" (withdrawn: {d['withdrawn']})" if d.get("withdrawn") else "")
                 for d in sheet.get("dependencies") or [] if isinstance(d, dict)]
    if not toolchain and not versions:
        return ""
    shown = ", ".join(versions[:24]) + (f", and {len(versions) - 24} more" if len(versions) > 24 else "")
    return (f"\n\n{TOOLCHAIN_LINE} {toolchain or 'not read'}.\n"
            f"{VERSIONS_LINE} {shown or 'none read yet'} (`.harness/stack-facts.json`).\n")


def release_gaps(root: str | Path | None) -> list[str]:
    """What the release ships against the facts: a withdrawn dependency, a toolchain mismatch left. [] when off."""
    if not enabled():
        return []
    sheet = read(root)
    gaps = [f"{WITHDRAWN_GAP} {d.get('package')} {d.get('resolved') or d.get('version')} ({d.get('withdrawn')})."
            for d in sheet.get("dependencies") or [] if isinstance(d, dict) and d.get("withdrawn")]
    for where, found in (sheet.get("mismatches") or {}).items():
        for m in found or []:
            if isinstance(m, dict):
                gaps.append(f"{MISFIT_GAP} {m.get('package')} {m.get('version')} in `{where}` needs {m.get('needs')}; "
                            f"the toolchain here is {m.get('toolchain')}.")
    return gaps


__all__ = ["MISFIT_GAP", "SHEET", "SWITCH", "TOOLCHAINS_HEADING", "TOOLCHAIN_LINE", "VERSIONS_LINE", "WITHDRAWN_GAP",
           "enabled", "fact",
           "for_a_fixer", "library_lines", "read", "release_gaps", "toolchain_line", "toolchains", "toolchains_section",
           "write"]
