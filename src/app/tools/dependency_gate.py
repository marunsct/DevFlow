"""An install fetches only packages its registry has, and none that appeared there days ago (deep review 2026-11-18, E2).

An install runs with a network (`sandbox.NETWORK_CATEGORIES`), and `install_egress` checks only the hosts it names.
Nothing checked the names. Open models invent package names often, and a name a model invents is one an attacker can
register: the next model that invents it installs whatever was put there, install scripts and all. So before an
install runs, each package it would bring - named on its command line, or declared in a manifest its package manager
reads in the directory it runs in - is looked up in its own registry (`package_registry.look_up`, the same lookup the
stages have):

- a name the registry does not have is refused;
- a package first published fewer than `DEPENDENCY_MIN_AGE_DAYS` days ago (14 by default) is refused: no model
  serving a run was trained on it, so it is an invented name that someone has just taken;
- a registry the harness cannot reach, an ecosystem it has no reader for, or a registry that does not say when a
  package first appeared lets the install through, and the verdict is recorded in `.harness/dependency-gate.json`.

Per-registry facts live in `REGISTRIES`: which package managers add from it, the manifests that declare its packages
and how to read them, and where its first publication date is. A package whose registry document is longer than
`ESTABLISHED_BYTES` has a long release history and is taken as established without reading the rest: a name taken
days ago has a document of a few kilobytes.

Optional and off (`INSTALL_SCRIPTS_SKIPPED`): an install run with its dependencies' own install scripts switched off,
by the flag each package manager has for it (`REGISTRIES[...].skip_scripts`). Some packages need their scripts (native
builds, downloaded binaries), so it is measured before it is kept.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Built in (`switches.BUILT_IN`): on. Its variable set off is a test's hook, so no test reaches a registry.
ON_BY_DEFAULT = False
#: The optional half: dependencies' install scripts switched off. Off until measured.
SCRIPTS_SKIPPED_SWITCH = "INSTALL_SCRIPTS_SKIPPED"

#: A registry document longer than this belongs to a package with a long release history.
ESTABLISHED_BYTES = 512 * 1024
#: How many packages are looked up at once.
AT_ONCE = 8
#: Where each verdict is kept, from the workspace root.
RECORD = ".harness/dependency-gate.json"
#: Seconds a registry that could not be reached is not asked again.
UNREACHABLE_FOR_SECONDS = 300.0

#: The first-publication date could not be read, but the package is long established.
ESTABLISHED = "established"


def enabled() -> bool:
    return is_on("DEPENDENCY_GATE", ON_BY_DEFAULT)


def scripts_skipped() -> bool:
    return is_on(SCRIPTS_SKIPPED_SWITCH, False)


def min_age_days() -> float:
    try:
        return max(0.0, float(os.environ.get("DEPENDENCY_MIN_AGE_DAYS", "14")))
    except ValueError:
        return 14.0


# --- reading what a manifest declares ---------------------------------------------------------------------------

def _json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _toml_file(path: Path) -> dict:
    try:
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable manifest declares nothing here
        return {}


def _npm_declared(directory: Path) -> list[str]:
    manifest = _json_file(directory / "package.json")
    if not isinstance(manifest, dict):
        return []
    names: list[str] = []
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        section = manifest.get(key)
        for name, spec in (section.items() if isinstance(section, dict) else ()):
            spec = str(spec or "").strip()
            if spec.startswith("npm:"):
                # An alias: the registry package is the one after `npm:`.
                names.append(re.sub(r"(?<=.)@[^@/]*$", "", spec[4:]))
            elif not re.match(r"^(?:file:|link:|workspace:|portal:|patch:|git|github:|gitlab:|bitbucket:|https?:|\.|/|~)", spec):
                names.append(str(name))
    return names


def _a_requirement(line: str) -> str:
    """The distribution a requirement line names from the index, or "" (a path, a URL, an option, a comment)."""
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", ".", "/")) or "://" in line or re.search(r"\s@\s", line):
        return ""
    return re.split(r"[\s;<>=!~@\[,]", line, maxsplit=1)[0].strip().lower()


def _pypi_declared(directory: Path) -> list[str]:
    names: list[str] = []
    for manifest in sorted(directory.glob("requirements*.txt")):
        try:
            names.extend(_a_requirement(line) for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    project = _toml_file(directory / "pyproject.toml").get("project") or {}
    names.extend(_a_requirement(str(item)) for item in project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        names.extend(_a_requirement(str(item)) for item in group or [])
    return [name for name in names if name]


def _crates_declared(directory: Path) -> list[str]:
    parsed = _toml_file(directory / "Cargo.toml")
    tables = [parsed.get(key) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
    for target in (parsed.get("target") or {}).values():
        if isinstance(target, dict):
            tables.extend(target.get(key) for key in ("dependencies", "dev-dependencies", "build-dependencies"))
    names: list[str] = []
    for table in tables:
        for name, spec in (table.items() if isinstance(table, dict) else ()):
            if isinstance(spec, dict):
                if spec.get("path") or spec.get("git") or spec.get("workspace"):
                    continue
                name = spec.get("package") or name
            names.append(str(name))
    return names


_A_GEM = re.compile(r"""^\s*gem\s+["']([^"']+)["'](.*)$""", re.M)


def _rubygems_declared(directory: Path) -> list[str]:
    try:
        text = (directory / "Gemfile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [name for name, rest in _A_GEM.findall(text) if not re.search(r"\b(?:path|git|github)\s*:", rest)]


def _packagist_declared(directory: Path) -> list[str]:
    manifest = _json_file(directory / "composer.json")
    if not isinstance(manifest, dict):
        return []
    names: list[str] = []
    for key in ("require", "require-dev"):
        section = manifest.get(key)
        names.extend(str(name) for name in (section if isinstance(section, dict) else ()) if "/" in str(name))
    return names


def _go_declared(directory: Path) -> list[str]:
    try:
        text = (directory / "go.mod").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    replaced = set(re.findall(r"^\s*(?:replace\s+)?(\S+)(?:\s+\S+)?\s*=>", text, re.M))
    required: list[str] = []
    for block in re.findall(r"^require\s*\((.*?)^\)", text, re.M | re.S):
        required.extend(re.findall(r"^\s*(\S+)\s+v\S+", block, re.M))
    required.extend(re.findall(r"^require\s+(\S+)\s+v\S+", text, re.M))
    return [module for module in required if module not in replaced]


_A_PACKAGE_REFERENCE = re.compile(r"""<PackageReference\s+[^>]*Include\s*=\s*["']([^"']+)["']""", re.I)


def _nuget_declared(directory: Path) -> list[str]:
    names: list[str] = []
    for project in sorted(directory.glob("*.csproj")):
        try:
            names.extend(_A_PACKAGE_REFERENCE.findall(project.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return names


# --- reading when a package first appeared ------------------------------------------------------------------------

def _date(text: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _earliest(dates: Iterable[Any]) -> datetime | None:
    found = [moment for moment in (_date(text) for text in dates if text) if moment]
    return min(found) if found else None


Fetch = Callable[[str], tuple[int, bytes]]


def _document(fetch: Fetch, url: str) -> Any:
    """The registry's JSON document, `ESTABLISHED` when longer than `ESTABLISHED_BYTES`, or None."""
    status, body = fetch(url)
    if status != 200:
        return None
    if len(body) > ESTABLISHED_BYTES:
        return ESTABLISHED
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _npm_first(name: str, fetch: Fetch) -> datetime | str | None:
    data = _document(fetch, f"https://registry.npmjs.org/{name}")
    if not isinstance(data, dict):
        return data
    return _date((data.get("time") or {}).get("created"))


def _pypi_first(name: str, fetch: Fetch) -> datetime | str | None:
    data = _document(fetch, f"https://pypi.org/pypi/{name}/json")
    if not isinstance(data, dict):
        return data
    files = [entry for entries in (data.get("releases") or {}).values() for entry in entries or []]
    return _earliest(entry.get("upload_time_iso_8601") or entry.get("upload_time") for entry in files)


def _crates_first(name: str, fetch: Fetch) -> datetime | str | None:
    data = _document(fetch, f"https://crates.io/api/v1/crates/{name}")
    if not isinstance(data, dict):
        return data
    return _date((data.get("crate") or {}).get("created_at"))


def _rubygems_first(name: str, fetch: Fetch) -> datetime | str | None:
    data = _document(fetch, f"https://rubygems.org/api/v1/versions/{name}.json")
    if not isinstance(data, list):
        return data if data == ESTABLISHED else None
    return _earliest(entry.get("created_at") for entry in data if isinstance(entry, dict))


def _packagist_first(name: str, fetch: Fetch) -> datetime | str | None:
    data = _document(fetch, f"https://repo.packagist.org/p2/{name.lower()}.json")
    if not isinstance(data, dict):
        return data
    releases = (data.get("packages") or {}).get(name.lower()) or []
    return _earliest(release.get("time") for release in releases if isinstance(release, dict))


# --- the table --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Registry:
    """What the gate knows of one registry; `ecosystem` is `package_registry`'s name for it."""

    ecosystem: str
    #: The package managers whose named additions come from it.
    managers: tuple[str, ...]
    #: The manifest files that declare its packages, and the reader of the folder they are in.
    manifests: tuple[str, ...] = ()
    declared: Callable[[Path], list[str]] | None = None
    #: When a package first appeared there; None where the registry does not say in one cheap read.
    first_published: Callable[[str, Fetch], datetime | str | None] | None = None
    #: The flags that switch dependencies' install scripts off, for the package managers that have one.
    skip_scripts: dict[str, tuple[str, ...]] = field(default_factory=dict)


REGISTRIES: dict[str, Registry] = {
    "npm": Registry(
        "npm", ("npm", "yarn", "pnpm", "bun"), ("package.json",), _npm_declared, _npm_first,
        # Yarn 2 and later ignore the flag (they read `enableScripts`); npm, pnpm, Yarn 1 and Bun honour it.
        {"npm": ("--ignore-scripts",), "pnpm": ("--ignore-scripts",), "yarn": ("--ignore-scripts",),
         "bun": ("--ignore-scripts",)},
    ),
    # pip, uv and Poetry have no flag that skips a source distribution's build, only one refusing every source
    # distribution (`--only-binary=:all:`), which fails on any package without a wheel: none here.
    "pypi": Registry("pypi", ("pip", "pip3", "uv", "poetry"), ("requirements.txt", "requirements-dev.txt", "pyproject.toml"),
                     _pypi_declared, _pypi_first),
    # A crate's build script is part of its build; there is nothing to switch off.
    "crates": Registry("crates", ("cargo",), ("Cargo.toml",), _crates_declared, _crates_first),
    "rubygems": Registry("rubygems", ("gem", "bundle"), ("Gemfile",), _rubygems_declared, _rubygems_first),
    "packagist": Registry(
        "packagist", ("composer",), ("composer.json",), _packagist_declared, _packagist_first,
        {"composer": ("--no-scripts", "--no-plugins")},
    ),
    # The Go proxy and NuGet's index say whether a package exists, not when it appeared in one read.
    "go": Registry("go", ("go",), ("go.mod",), _go_declared),
    "nuget": Registry("nuget", ("dotnet",), (), _nuget_declared),
}

_BY_MANAGER = {manager: registry for registry in REGISTRIES.values() for manager in registry.managers}


# --- the check --------------------------------------------------------------------------------------------------

_VERDICTS: dict[tuple[str, str], dict[str, Any]] = {}
_UNREACHABLE: dict[str, float] = {}
_LOCK = threading.Lock()


def _bare(name: str) -> str:
    """`name` without the version asked for: `left-pad@1.3.0`, `requests==2.32`, `serde@1`."""
    found = re.match(r"^(@?[^@=<>!~^\s\[]+)", name.strip())
    return found.group(1) if found else ""


#: Options whose next word is a value - a version, a source, a group, a file - never a package to look up.
_FLAGS_WITH_A_VALUE = frozenset({
    "--version", "--source", "-s", "--framework", "-f", "--package-directory", "-c", "--constraint", "--group",
    "--groups", "--features", "-F", "--rename", "--branch", "--tag", "--rev", "--git", "--path", "--registry", "--index",
    "--index-url", "--extra-index-url", "--prefix", "-C", "--cwd", "--dir", "--directory", "--root", "--project",
    "--manifest-path", "--target", "--target-dir", "--python", "--filter", "--cache", "--cache-dir", "--config",
    # An editable install names the project's own folder (or a source address), never a registry's package. Measured on
    # one run: `pip install -e task-management-dashboard/backend[test]` was refused as a name the registry never had.
    "-e", "--editable",
})


def _named_on_the_command_line(command: Sequence[str]) -> list[str]:
    """The packages an install names, as its registry spells them: no version, no path, no URL, no option's value."""
    from app.tools.sandbox import _a_package_this_command_would_add

    words = [str(word) for word in command]
    values = {words[i + 1] for i, word in enumerate(words[:-1]) if word in _FLAGS_WITH_A_VALUE}
    names = []
    for word in _a_package_this_command_would_add(command):
        if word in values or re.match(r"^(?:\.|/|~|file:|git|https?:|link:|v?\d)", word) or "://" in word:
            continue  # a value, a version, a path or a URL: `install_egress` has the say on where
        name = _bare(word)
        if name:
            names.append(name)
    return names


def _what_it_would_bring(command: Sequence[str], directory: Path) -> list[tuple[Registry, str, str]]:
    """(registry, package, where it is named) for each package this install would fetch: those its command line names
    and those its package manager's manifests declare in the folder it runs in. [] for a manager no registry here has."""
    from app.tools.sandbox import _manager_of

    registry = _BY_MANAGER.get(_manager_of(command) or "")
    if registry is None:
        return []
    found = [(registry, name, "the command line") for name in _named_on_the_command_line(command)]
    present = [name for name in registry.manifests if (directory / name).is_file()]
    if registry.declared is not None and (present or not registry.manifests):
        try:
            declared = registry.declared(directory)
        except Exception:  # noqa: BLE001 - an unreadable manifest declares nothing here
            declared = []
        where = ", ".join(present) or "the project's manifest"
        found.extend((registry, name, where) for name in declared)
    seen: set[str] = set()
    return [item for item in found if not (item[1] in seen or seen.add(item[1]))]


def _fetch(url: str) -> tuple[int, bytes]:
    """A registry read that stops just past `ESTABLISHED_BYTES`: past that, the rest is not needed."""
    from app.tools import package_registry

    return package_registry._fetch(url, ESTABLISHED_BYTES)


def _verdict(registry: Registry, name: str) -> dict[str, Any]:
    """{"verdict": "allowed" | "missing" | "too new" | "unverified", ...} for one package. Never raises."""
    from app.tools import package_registry

    key = (registry.ecosystem, name)
    with _LOCK:
        if key in _VERDICTS:
            return _VERDICTS[key]
        if time.monotonic() < _UNREACHABLE.get(registry.ecosystem, 0.0):
            return {"verdict": "unverified", "why": f"the {registry.ecosystem} registry could not be reached"}
    try:
        found = package_registry.look_up(registry.ecosystem, name)
    except Exception as exc:  # noqa: BLE001 - an unreachable registry lets the install through
        found = {"error": type(exc).__name__}
    if found.get("missing"):
        outcome: dict[str, Any] = {"verdict": "missing"}
    elif "error" in found:
        if "could not be read" in str(found.get("error")):
            with _LOCK:
                _UNREACHABLE[registry.ecosystem] = time.monotonic() + UNREACHABLE_FOR_SECONDS
        return {"verdict": "unverified", "why": str(found.get("error"))[:200]}
    elif registry.first_published is None:
        outcome = {"verdict": "allowed", "why": "the registry does not say when it first appeared"}
    else:
        try:
            first = registry.first_published(name, _fetch)
        except Exception as exc:  # noqa: BLE001 - its age unknown, it goes through
            first = None
            logger.info("Could not read when %s %s first appeared: %s", registry.ecosystem, name, exc)
        if isinstance(first, datetime):
            days = (datetime.now(timezone.utc) - first).total_seconds() / 86400
            outcome = ({"verdict": "too new", "days": round(days, 1), "first": first.date().isoformat()}
                       if days < min_age_days() else {"verdict": "allowed", "first": first.date().isoformat()})
        elif first == ESTABLISHED:
            outcome = {"verdict": "allowed", "why": "a long release history"}
        else:
            return {"verdict": "unverified", "why": "when it first appeared could not be read"}
    with _LOCK:
        _VERDICTS[key] = outcome
    return outcome


def _record(repo_root: str | Path | None, verdicts: dict[str, dict[str, Any]]) -> None:
    """Keep each verdict in the workspace, beside the run's other records. Never raises."""
    if not repo_root or not verdicts:
        return
    try:
        path = Path(repo_root) / RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        kept = _json_file(path) if path.is_file() else {}
        kept = kept if isinstance(kept, dict) else {}
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        kept.update({key: {**value, "at": stamp} for key, value in verdicts.items()})
        path.write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 - the install's verdict stands without its record
        logger.debug("Could not record the dependency verdicts", exc_info=True)


def refusal(command: Sequence[str], directory: str | Path, repo_root: str | Path | None = None) -> str:
    """Why this install may not run - a package its registry does not have, or one only days old; "" otherwise. Never raises."""
    try:
        if not enabled():
            return ""
        from app.tools import package_registry

        if not package_registry.enabled():
            return ""
        wanted = _what_it_would_bring(command, Path(directory))
        if not wanted:
            return ""
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            verdicts = list(pool.map(lambda item: _verdict(item[0], item[1]), wanted))
        _record(repo_root, {f"{registry.ecosystem}:{name}": verdict
                            for (registry, name, _), verdict in zip(wanted, verdicts)})
        refused = [(registry, name, where, verdict) for (registry, name, where), verdict in zip(wanted, verdicts)
                   if verdict["verdict"] in ("missing", "too new")]
        if not refused:
            return ""
        lines = []
        for registry, name, where, verdict in refused[:6]:
            if verdict["verdict"] == "missing":
                lines.append(f"- `{name}` ({where}): the {registry.ecosystem} registry has no package of that name.")
            else:
                lines.append(f"- `{name}` ({where}): first published to the {registry.ecosystem} registry on "
                             f"{verdict['first']}, {verdict['days']:g} days ago.")
        return (
            "Not installing: this would fetch packages that are not safe to fetch.\n" + "\n".join(lines) + "\n"
            f"A name the registry does not have is a name that was never published; a package younger than "
            f"{min_age_days():g} days is one no model here was trained on - most often a name someone else invented "
            "and has just taken. Check each with `look_up_package`, use the package the registry has under its real "
            "name, or do without it, and remove the name from the manifest that declares it."
        )
    except Exception:  # noqa: BLE001 - the install goes on as it would have
        logger.debug("The dependency gate could not run", exc_info=True)
        return ""


def with_scripts_skipped(command: Sequence[str]) -> list[str]:
    """`command`, with its package manager's flag that switches dependencies' install scripts off, when
    `INSTALL_SCRIPTS_SKIPPED` is on and the manager has one; as it was otherwise."""
    argv = [str(part) for part in command]
    if not scripts_skipped():
        return argv
    from app.tools.sandbox import _fetches_dependencies, _manager_of

    manager = _manager_of(argv) or ""
    registry = _BY_MANAGER.get(manager)
    flags = registry.skip_scripts.get(manager, ()) if registry else ()
    if not flags or not _fetches_dependencies(argv):
        return argv
    return argv + [flag for flag in flags if flag not in argv]


__all__ = ["ESTABLISHED_BYTES", "ON_BY_DEFAULT", "RECORD", "REGISTRIES", "Registry", "enabled", "min_age_days",
           "refusal", "scripts_skipped", "with_scripts_skipped"]
