"""What the packages installed in a project say for themselves: the names they really have, the version on disk and
their own changelogs - local truth, read before anything is asked of the web (plan HK.3(a), LF.1295).

A stuck error that says a package has no such name (`cannot import name 'X' from 'pkg'`, `Module '"pkg"' has no
exported member 'X'`, `does not provide an export named 'X'`, a subpath the package does not export, rustc's
`unresolved import`) is answered from the package's own files: the names it exports
(`app.analysis.package_exports`), or where a crate really declares the name (`app.analysis.rust_crate_exports`), and
the lines of its shipped changelog that mention the name, under the release heading they sit in. Measured before:
the stuck lookup sent such errors to the web, which knows the package's names only as of whatever release someone
wrote about, while the installed release's own files were on disk; the Rust mechanism (LF.1281) answered them at
compile time for Rust alone.

The version of a package is read from the stack facts the harness keeps (`.harness/stack-facts.json`, plan HK.1)
when they name it, else from the installed files (an npm package's `package.json`, a Python distribution's
`.dist-info`, a crate unpacked by cargo). Nothing of a package is run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The stack facts file (plan HK.1); read when present, never required.
FACTS_FILE = ".harness/stack-facts.json"
#: Names listed from a package that has no name asked for.
MOST_NAMES_SHOWN = 25
#: Changelog lines quoted for a name.
MOST_CHANGELOG_LINES = 4
#: Bytes of one changelog read.
MOST_CHANGELOG_BYTES = 400_000
#: A package's shipped history files.
_CHANGELOGS = ("CHANGELOG.md", "CHANGELOG", "CHANGELOG.rst", "CHANGELOG.txt", "CHANGES.md", "CHANGES.rst",
               "CHANGES", "HISTORY.md", "HISTORY.rst", "NEWS.md", "NEWS", "RELEASES.md", "docs/CHANGELOG.md")


# --- what an error says is missing --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Missing:
    """A name an error says a package does not have: the package (as code names it), the name, the language family
    ("python", "script" or "rust"), and the subpath a script import asked for when that is what is missing."""

    package: str
    name: str
    family: str
    subpath: bool = False


_PYTHON_IMPORT = re.compile(r"cannot import name ['\"]([\w.]+)['\"] from ['\"]([\w.]+)['\"]")
_PYTHON_ATTRIBUTE = re.compile(r"module ['\"]([\w.]+)['\"] has no attribute ['\"](\w+)['\"]")
_SCRIPT_MEMBER = re.compile(r"""Module ['"]{1,2}([@\w./-]+)['"]{1,2} has no exported member(?: named)? ['"]([\w$]+)['"]""")
_SCRIPT_EXPORT = re.compile(r"""requested module ['"]([@\w./-]+)['"] does not provide an export named ['"]([\w$]+)['"]""")
_SCRIPT_SUBPATH = re.compile(r"""Package subpath ['"]\./([\w./-]+)['"] is not defined by "exports" in \S*?node_modules/((?:@[\w.-]+/)?[\w.-]+)/package\.json""")
_RUST_PATH = re.compile(r"unresolved import `([A-Za-z_]\w*)::[^`]+`|(?:no|cannot find [a-z ,]+|could not find) `([A-Za-z_]\w*)` in "
                        r"(?:(?:crate|module|enum) )?`([A-Za-z_]\w*)")
#: rustc's E0432 for a crate the project never declared: "unresolved import `http_body_util`".
_RUST_CRATE = re.compile(r"unresolved import `([A-Za-z_]\w*)`")
#: rustc's E0599 for a name a crate's type has not: "no method named `as_ref` found for struct `tokio::sync::X<..>`".
_RUST_MEMBER = re.compile(r"no (?:method|function|variant|associated item|variant or associated item|function or "
                          r"associated item) named `(\w+)` found for (?:struct|enum|trait|union) `([A-Za-z_]\w*)::")


def missing_in(error: str) -> Missing | None:
    """The package and name `error` says is missing, or None when it says no such thing."""
    text = str(error or "")
    if found := _PYTHON_IMPORT.search(text):
        return Missing(found.group(2), found.group(1), "python")
    if found := _PYTHON_ATTRIBUTE.search(text):
        return Missing(found.group(1), found.group(2), "python")
    if found := _SCRIPT_MEMBER.search(text) or _SCRIPT_EXPORT.search(text):
        return Missing(found.group(1), found.group(2), "script")
    if found := _SCRIPT_SUBPATH.search(text):
        return Missing(found.group(2), found.group(1), "script", subpath=True)
    # Measured on real rustc output (deep review of the parsers, 2026-11-25): E0433's "could not find `X` in `y`",
    # E0425's "in crate `y`", a crate never declared (E0432 with one name) and E0599's name a crate's type lacks
    # were read as nothing, so the installed crate was never asked about them.
    for pattern, crate_at, name_at in ((_RUST_PATH, (1, 3), 2), (_RUST_CRATE, (1,), 0), (_RUST_MEMBER, (2,), 1)):
        if found := pattern.search(text):
            crate = next((found.group(i) for i in crate_at if found.group(i)), "")
            if crate not in _NOT_A_CRATE:
                return Missing(crate, (found.group(name_at) or "") if name_at else "", "rust")
    return None


#: The first segments of a Rust path that name no crate.
_NOT_A_CRATE = frozenset({"", "crate", "self", "super", "std", "core", "alloc", "Self"})


# --- where a project's packages are ---------------------------------------------------------------------------------

def project_of(repo_root: str | Path) -> Path:
    """The project's own directory in a workspace: the pinned one, else the workspace."""
    root = Path(repo_root)
    try:
        from app.tools.repository import pinned_project_directory

        pinned = pinned_project_directory(root)
    except Exception:  # noqa: BLE001 - the workspace itself
        pinned = None
    return root / pinned if pinned else root


def _bases(project: Path) -> tuple[Path, ...]:
    return (project, project.parent)


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name or "").strip().lower())


def package_directory(project: Path, family: str, package: str) -> Path | None:
    """Where an installed package's files are: `node_modules/<name>`, a Python distribution's import directory, or
    the crate cargo unpacked. None when it is not installed here."""
    top = package.split("/")[0] if not package.startswith("@") else "/".join(package.split("/")[:2])
    for base in _bases(project):
        if family == "script" and (base / "node_modules" / top).is_dir():
            return base / "node_modules" / top
        if family == "python":
            for site in sorted((base / ".venv" / "lib").glob("python*/site-packages")):
                if (site / package.split(".")[0]).is_dir():
                    return site / package.split(".")[0]
    if family == "rust":
        try:
            from app.analysis.rust_crate_exports import Registry

            registry = Registry(project)
            chosen = getattr(registry, "_chosen", {}).get(package.replace("-", "_"))
            return Path(chosen[0]) if chosen else None
        except Exception:  # noqa: BLE001 - not unpacked here
            return None
    return None


def _distribution(project: Path, package: str) -> Path | None:
    """A Python package's `.dist-info` directory, by its distribution or import name."""
    wanted = _normal(package.split(".")[0])
    for base in _bases(project):
        for site in sorted((base / ".venv" / "lib").glob("python*/site-packages")):
            for info in site.glob("*.dist-info"):
                name = info.name[: -len(".dist-info")].rsplit("-", 1)[0]
                if _normal(name) == wanted:
                    return info
                try:
                    tops = (info / "top_level.txt").read_text(encoding="utf-8").split()
                except OSError:
                    tops = []
                if wanted in {_normal(t) for t in tops}:
                    return info
    return None


# --- versions: the stack facts first, the installed files after -----------------------------------------------------

def _facts_entries(data: Any) -> list[dict[str, Any]]:
    """The facts file's packages as dicts with at least a name, whichever of the shapes it is kept in."""
    entries: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return entries
    for key in ("dependencies", "packages", "libraries"):
        value = data.get(key)
        if isinstance(value, list):
            entries += [v for v in value if isinstance(v, dict) and (v.get("name") or v.get("package"))]
        elif isinstance(value, dict):
            for name, fact in value.items():
                if isinstance(fact, dict):
                    entries.append({"name": name, **fact})
                elif isinstance(fact, str):
                    entries.append({"name": name, "version": fact})
    return entries


def stack_facts(repo_root: str | Path) -> dict[str, dict[str, Any]]:
    """The facts the harness keeps on each package (plan HK.1, `app.stacks.stack_facts`), by normalised name: the
    version the project resolved (else the release chosen for it), its release date, homes and ecosystem - whichever
    the sheet gives. {} when there is no sheet or it cannot be read."""
    try:
        from app.stacks import stack_facts as sheet

        data = sheet.read(repo_root)
    except Exception:  # noqa: BLE001 - the sheet read as a file
        try:
            data = json.loads((Path(repo_root) / FACTS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    found: dict[str, dict[str, Any]] = {}
    for entry in _facts_entries(data):
        name = str(entry.get("name") or entry.get("package") or "")
        version = str(entry.get("resolved") or entry.get("installed") or entry.get("version") or entry.get("chosen")
                      or entry.get("release") or "")
        released = str(entry.get("released") or entry.get("release_date") or entry.get("date") or "")[:10]
        homes = entry.get("homes") or [h for h in (entry.get("repository"), entry.get("homepage")) if h]
        found[_normal(name)] = {"name": name, "version": version.lstrip("v=^~ "), "released": released,
                                "homes": [str(h) for h in homes if h] if isinstance(homes, list) else [str(homes)],
                                "ecosystem": str(entry.get("ecosystem") or "")}
    return found


def installed_version(repo_root: str | Path, package: str, family: str = "") -> str:
    """The version of `package` this project runs: the stack facts' when they name it, else the installed files';
    "" when neither says."""
    fact = stack_facts(repo_root).get(_normal(package)) or stack_facts(repo_root).get(_normal(package.split("/")[0]))
    if fact and fact.get("version"):
        return str(fact["version"])
    project = project_of(repo_root)
    families = [family] if family else ["script", "python", "rust"]
    for each in families:
        if each == "script":
            directory = package_directory(project, "script", package)
            try:
                version = json.loads((directory / "package.json").read_text(encoding="utf-8")).get("version") \
                    if directory else ""
            except (OSError, ValueError):
                version = ""
            if version:
                return str(version)
        if each == "python":
            info = _distribution(project, package)
            if info is not None:
                return info.name[: -len(".dist-info")].rsplit("-", 1)[-1]
        if each == "rust":
            try:
                from app.analysis.rust_crate_exports import Registry

                version = Registry(project).version(package)
            except Exception:  # noqa: BLE001
                version = ""
            if version:
                return version
    return ""


def released(repo_root: str | Path, package: str) -> str:
    """The release date (YYYY-MM-DD) the stack facts give for the version of `package` this project runs, or ""."""
    fact = stack_facts(repo_root).get(_normal(package)) or {}
    return str(fact.get("released") or "")


# --- the package's own changelog -------------------------------------------------------------------------------------

_A_HEADING = re.compile(r"^(?:#{1,4}\s*\[?v?(\d+\.\d+[\w.+-]*)|v?(\d+\.\d+(?:\.\d+)?[\w.+-]*)\s*(?:\(|-|$))")


def changelog_lines(directory: Path | None, name: str, project: Path | None = None, package: str = "") -> list[str]:
    """The lines of an installed package's shipped history that mention `name`, each with the release heading it
    sits under: "CHANGELOG.md, 4.0.0: - `createClient` was renamed to `testClient`"."""
    if not name:
        return []
    places = [directory / file for file in _CHANGELOGS] if directory else []
    if project is not None and package:
        info = _distribution(project, package)
        if info is not None:
            places.append(info / "METADATA")
    word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
    found: list[str] = []
    for place in places:
        try:
            if not place.is_file():
                continue
            text = place.read_bytes()[:MOST_CHANGELOG_BYTES].decode("utf-8", errors="replace")
        except OSError:
            continue
        release = ""
        for line in text.splitlines():
            heading = _A_HEADING.match(line.strip())
            if heading:
                release = heading.group(1) or heading.group(2)
            if word.search(line):
                found.append(f"{place.name}{', ' + release if release else ''}: {' '.join(line.split())[:240]}")
                if len(found) >= MOST_CHANGELOG_LINES:
                    return found
    return found


# --- the answer -----------------------------------------------------------------------------------------------------

@dataclass
class LocalAnswer:
    """What the installed package's files say about a missing name."""

    package: str
    version: str
    sentence: str
    changelog: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        said = self.sentence.strip().rstrip(".") + "."
        # rustc's answer names the crate and its version itself.
        lines = [said if said.startswith("`") else f"`{self.package}` {self.version}".rstrip() + ": " + said]
        if self.changelog:
            lines.append("Its changelog, as installed, on that name:")
            lines += [f"- {line}" for line in self.changelog]
        return "\n".join(lines)


def _names_sentence(names: list[str], wanted: str) -> str:
    import difflib

    near = [n for n in names if wanted and (wanted.lower() in n.lower() or n.lower() in wanted.lower())]
    near += difflib.get_close_matches(wanted, names, n=5, cutoff=0.6) if wanted else []
    near = list(dict.fromkeys(near))[:5]
    shown = ", ".join(f"`{n}`" for n in names[:MOST_NAMES_SHOWN]) or "nothing readable"
    said = f" it has no `{wanted}`; it exports only: {shown}"
    if near:
        said += f". The nearest names: {', '.join(f'`{n}`' for n in near)}"
    return said + " - use one of those, or write the function yourself"


def answer(repo_root: str | Path, error: str) -> LocalAnswer | None:
    """What the installed package's own files say about the name `error` says is missing; None when the error names
    no missing name or the package is not installed here. Never raises."""
    try:
        missing = missing_in(error)
        if missing is None:
            return None
        project = project_of(repo_root)
        from app.analysis import package_exports

        sentence = ""
        if missing.family == "rust":
            from app.analysis.rust_crate_exports import where_it_is

            sentence = where_it_is(project, project / "src" / "main.rs", {"message": error})
        elif missing.subpath:
            paths = package_exports.package_paths(project, f"{missing.package}/{missing.name}")
            if paths:
                sentence = (f" it does not export the path `{missing.package}/{missing.name}`; the paths it exports: "
                            + ", ".join(f"`{p}`" for p in paths[:MOST_NAMES_SHOWN]))
        else:
            read = (package_exports.script_package_exports if missing.family == "script"
                    else package_exports.python_package_exports)
            names = read(project, missing.package)
            if names is not None:
                sentence = _names_sentence(names, missing.name)
        if not sentence:
            return None
        top = missing.package.split(".")[0] if missing.family == "python" else missing.package
        directory = package_directory(project, missing.family, missing.package)
        lines = changelog_lines(directory, missing.name, project if missing.family == "python" else None, top)
        return LocalAnswer(package=missing.package, version=installed_version(repo_root, top, missing.family),
                           sentence=sentence, changelog=lines)
    except Exception:  # noqa: BLE001 - the web is asked as before
        return None


__all__ = ["FACTS_FILE", "LocalAnswer", "Missing", "answer", "changelog_lines", "installed_version", "missing_in",
           "package_directory", "project_of", "released", "stack_facts"]
