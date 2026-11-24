"""The packages an install resolved, with the runtime each says it needs where the project's files say it (HK.2).

One reader per kind of lock file, named by the language table (`LanguageSupport.resolved`): the stack specifics of
reading a lock file live here and in that table, nowhere else. Each reads what the install wrote - the lock file, the
restore's assets, the installed packages' own metadata - and, where the install failed before writing one, the exact
versions the manifest pins, so a pin no release of this toolchain can run is seen too (measured: a C# project pinned a
package release that targets net10.0 only under .NET 8, and every restore failed NU1202).

A package's need is read locally where the files carry it (npm's lock keeps `engines`, Composer's keeps
`require.php`, a crate's unpacked `Cargo.toml` its `rust-version`, a Go module's cached `go.mod` its `go` directive, an
installed Python distribution its `Requires-Python`, a NuGet restore the frameworks each package ships). Where they do
not, `needs` is None and the registry is asked for that release (`app.tools.release_fit.needs_of`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: The sandbox's HOME, under the workspace: where cargo and Go keep what they fetched (`sandbox._child_environment`).
SANDBOX_HOME = ".agent-home"
#: The most entries read from one lock file.
MOST_ENTRIES = 600


@dataclass(frozen=True)
class Resolved:
    ecosystem: str
    name: str
    version: str
    #: The runtime it needs as its files state it; "" when they state none; None when they do not say (ask its registry).
    needs: str | None
    #: The file it was read from, relative to the folder read.
    source: str
    #: Declared by the project itself, not brought by another package.
    direct: bool


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _json(path: Path) -> object:
    try:
        return json.loads(_text(path))
    except ValueError:
        return None


def _toml(path: Path) -> dict:
    try:
        import tomllib

        return tomllib.loads(_text(path))
    except Exception:  # noqa: BLE001 - an unreadable file says nothing
        return {}


_EXACT = re.compile(r"^=?=?\s*v?(\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?)$")


def _home(directory: Path, workspace: Path | None) -> Path:
    return (workspace or directory) / SANDBOX_HOME


# --- npm --------------------------------------------------------------------------------------------------------

def _npm(directory: Path, workspace: Path | None) -> list[Resolved]:
    manifest = _json(directory / "package.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    declared: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        section = manifest.get(key)
        declared.update({str(k): str(v) for k, v in (section.items() if isinstance(section, dict) else ())})
    lock = _json(directory / "package-lock.json")
    found: list[Resolved] = []
    if isinstance(lock, dict) and isinstance(lock.get("packages"), dict):
        for key, entry in lock["packages"].items():
            if not key or not isinstance(entry, dict) or entry.get("link") or not entry.get("version"):
                continue
            name = str(entry.get("name") or key.rsplit("node_modules/", 1)[-1])
            engines = entry.get("engines")
            needs = str(engines.get("node") or "") if isinstance(engines, dict) else ""
            found.append(Resolved("npm", name, str(entry["version"]), needs, "package-lock.json",
                                  key == f"node_modules/{name}" and name in declared))
    elif isinstance(lock, dict) and isinstance(lock.get("dependencies"), dict):
        for name, entry in lock["dependencies"].items():
            if isinstance(entry, dict) and entry.get("version"):
                found.append(Resolved("npm", str(name), str(entry["version"]), None, "package-lock.json",
                                      name in declared))
    if not found:
        for name, spec in declared.items():
            exact = _EXACT.match(spec.strip())
            if exact:
                found.append(Resolved("npm", name, exact.group(1), None, "package.json", True))
    return found


# --- Python -----------------------------------------------------------------------------------------------------

def _distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _python(directory: Path, workspace: Path | None) -> list[Resolved]:
    declared: dict[str, str] = {}
    for manifest in sorted(directory.glob("requirements*.txt")):
        for line in _text(manifest).splitlines():
            line = line.split("#", 1)[0].strip()
            pinned = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([0-9][0-9A-Za-z.+-]*)\s*(?:;.*)?$", line)
            named = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if named and not line.startswith("-"):
                declared[_distribution(named.group(1))] = pinned.group(2) if pinned else ""
    project = _toml(directory / "pyproject.toml").get("project") or {}
    for item in project.get("dependencies") or []:
        named = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(item))
        if named:
            declared.setdefault(_distribution(named.group(1)), "")
    found: dict[str, Resolved] = {}
    for lock in (directory / "poetry.lock", directory / "uv.lock"):
        for package in _toml(lock).get("package") or []:
            if isinstance(package, dict) and package.get("name") and package.get("version"):
                name = _distribution(str(package["name"]))
                needs = package.get("python-versions") or package.get("requires-python")
                found[name] = Resolved("pypi", name, str(package["version"]), str(needs) if needs and needs != "*" else "",
                                       lock.name, name in declared)
    for venv in (directory / ".venv", directory / "venv"):
        for metadata in sorted(venv.glob("lib/python*/site-packages/*.dist-info/METADATA"))[:MOST_ENTRIES]:
            head = _text(metadata).split("\n\n", 1)[0]
            name = re.search(r"^Name:\s*(\S+)", head, re.M)
            version = re.search(r"^Version:\s*(\S+)", head, re.M)
            if not name or not version:
                continue
            needs = re.search(r"^Requires-Python:\s*(.+)$", head, re.M)
            key = _distribution(name.group(1))
            found.setdefault(key, Resolved("pypi", key, version.group(1), needs.group(1).strip() if needs else "",
                                           f"{venv.name}/.../{metadata.parent.name}", key in declared))
    for name, version in declared.items():
        if version and name not in found:
            found[name] = Resolved("pypi", name, version, None, "requirements.txt", True)
    return list(found.values())


# --- Rust -------------------------------------------------------------------------------------------------------

def _rust(directory: Path, workspace: Path | None) -> list[Resolved]:
    manifest = _toml(directory / "Cargo.toml")
    declared = set()
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        table = manifest.get(key)
        for name, spec in (table.items() if isinstance(table, dict) else ()):
            declared.add(str(spec.get("package") or name) if isinstance(spec, dict) else str(name))
    unpacked = _home(directory, workspace) / ".cargo" / "registry" / "src"
    found = []
    for package in (_toml(directory / "Cargo.lock").get("package") or [])[:MOST_ENTRIES]:
        if not isinstance(package, dict) or not str(package.get("source") or "").startswith(("registry+", "sparse+")):
            continue
        name, version = str(package.get("name") or ""), str(package.get("version") or "")
        needs = None
        for crate in unpacked.glob(f"*/{name}-{version}/Cargo.toml"):
            stated = (_toml(crate).get("package") or {}).get("rust-version")
            needs = str(stated) if isinstance(stated, (str, int, float)) else ""
            break
        found.append(Resolved("crates", name, version, needs, "Cargo.lock", name in declared))
    return found


# --- Go ---------------------------------------------------------------------------------------------------------

def _go(directory: Path, workspace: Path | None) -> list[Resolved]:
    text = _text(directory / "go.mod")
    if not text:
        return []
    requires: list[tuple[str, str, bool]] = []
    for block in re.findall(r"^require\s*\((.*?)^\)", text, re.M | re.S):
        requires.extend((m, v, "// indirect" not in rest)
                        for m, v, rest in re.findall(r"^\s*(\S+)\s+(v\S+)(.*)$", block, re.M))
    requires.extend((m, v, "// indirect" not in rest) for m, v, rest in re.findall(r"^require\s+(\S+)\s+(v\S+)(.*)$", text, re.M))
    cache = _home(directory, workspace) / "go" / "pkg" / "mod" / "cache" / "download"
    found = []
    for module, version, direct in requires[:MOST_ENTRIES]:
        escaped = re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module)
        mod = _text(cache / escaped / "@v" / f"{version}.mod")
        directive = re.search(r"^go\s+(\d+(?:\.\d+)*)", mod, re.M) if mod else None
        found.append(Resolved("go", module, version, (directive.group(1) if directive else "") if mod else None,
                              "go.mod", direct))
    return found


# --- Ruby -------------------------------------------------------------------------------------------------------

def _ruby(directory: Path, workspace: Path | None) -> list[Resolved]:
    lock = _text(directory / "Gemfile.lock")
    found = []
    if lock:
        dependencies = re.search(r"^DEPENDENCIES\n((?:  .*\n?)*)", lock, re.M)
        declared = set(re.findall(r"^  ([A-Za-z0-9_.-]+)", dependencies.group(1), re.M)) if dependencies else set()
        for gem in re.finditer(r"^GEM\n(?:.*\n)*?  specs:\n((?:    .*\n?)*)", lock, re.M):
            for name, version in re.findall(r"^    ([A-Za-z0-9_.-]+) \(([^)\s]+)\)", gem.group(1), re.M)[:MOST_ENTRIES]:
                version = re.sub(r"-(?:x86|arm|aarch|universal|java|x64)[\w-]*$", "", version)
                found.append(Resolved("rubygems", name, version, None, "Gemfile.lock", name in declared))
        return found
    for name, version in re.findall(r"""^\s*gem\s+["']([^"']+)["']\s*,\s*["']=?\s*(\d+\.\d+\.\d+)["']""",
                                    _text(directory / "Gemfile"), re.M):
        found.append(Resolved("rubygems", name, version, None, "Gemfile", True))
    return found


# --- PHP --------------------------------------------------------------------------------------------------------

def _php(directory: Path, workspace: Path | None) -> list[Resolved]:
    manifest = _json(directory / "composer.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    declared = {str(n) for key in ("require", "require-dev") for n in (manifest.get(key) or {}) if "/" in str(n)}
    lock = _json(directory / "composer.lock")
    found = []
    if isinstance(lock, dict):
        for key in ("packages", "packages-dev"):
            for package in (lock.get(key) or [])[:MOST_ENTRIES]:
                if not isinstance(package, dict) or not package.get("name") or not package.get("version"):
                    continue
                requires = package.get("require") if isinstance(package.get("require"), dict) else {}
                found.append(Resolved("packagist", str(package["name"]), str(package["version"]).lstrip("v"),
                                      str(requires.get("php") or ""), "composer.lock", package["name"] in declared))
    return found


# --- .NET -------------------------------------------------------------------------------------------------------

_A_REFERENCE = re.compile(r"""<PackageReference\s+([^>]*)/?>""", re.I)


def _framework_folders(files: list[str]) -> str:
    """The target frameworks a NuGet package ships assemblies for, from its `lib/<tfm>/` and `ref/<tfm>/` files."""
    folders = [m.group(1) for f in files for m in [re.match(r"^(?:lib|ref)/([^/]+)/", str(f))] if m]
    return ";".join(dict.fromkeys(folders))


def _dotnet(directory: Path, workspace: Path | None) -> list[Resolved]:
    found: dict[tuple[str, str], Resolved] = {}
    declared: dict[str, str] = {}
    for project in sorted(directory.glob("*.csproj")) + sorted(directory.glob("*.fsproj")):
        for attributes in _A_REFERENCE.findall(_text(project)):
            name = re.search(r"""Include\s*=\s*["']([^"']+)["']""", attributes)
            version = re.search(r"""Version\s*=\s*["']\[?([0-9][^"',\]]*)""", attributes)
            if name:
                declared[name.group(1).lower()] = version.group(1) if version else ""
        assets = _json(project.parent / "obj" / "project.assets.json")
        libraries = assets.get("libraries") if isinstance(assets, dict) else None
        for key, library in (libraries.items() if isinstance(libraries, dict) else ()):
            if not isinstance(library, dict) or library.get("type") != "package" or "/" not in key:
                continue
            name, version = key.split("/", 1)
            found[(name.lower(), version)] = Resolved("nuget", name, version, _framework_folders(library.get("files") or []),
                                                      "obj/project.assets.json", name.lower() in declared)
    names = {name for name, _ in found}
    for project in sorted(directory.glob("*.csproj")) + sorted(directory.glob("*.fsproj")):
        for attributes in _A_REFERENCE.findall(_text(project)):
            name = re.search(r"""Include\s*=\s*["']([^"']+)["']""", attributes)
            version = re.search(r"""Version\s*=\s*["']\[?([0-9][^"',\]]*)""", attributes)
            if name and version and name.group(1).lower() not in names:
                found[(name.group(1).lower(), version.group(1))] = Resolved(
                    "nuget", name.group(1), version.group(1), None, project.name, True)
    return list(found.values())


#: Each reader by the name the language table gives it (`LanguageSupport.resolved`).
READERS: dict[str, Callable[[Path, Path | None], list[Resolved]]] = {
    "npm": _npm, "python": _python, "cargo": _rust, "go": _go, "bundler": _ruby, "composer": _php, "nuget": _dotnet,
}

#: The files whose change means an install resolved again, beyond the language table's lock files.
RESOLUTION_FILES = ("obj/project.assets.json",)


def resolved_in(directory: str | Path, workspace: str | Path | None = None) -> list[Resolved]:
    """Every package resolved for the projects in `directory`, by each language whose manifest is there. Never raises."""
    import fnmatch

    from app.stacks.languages import LANGUAGES, Gap

    directory = Path(directory)
    try:
        names = [p.name for p in directory.iterdir() if p.is_file()]
    except OSError:
        return []
    out: list[Resolved] = []
    seen_readers: set[str] = set()
    for row in LANGUAGES:
        reader = row.resolved
        if isinstance(reader, Gap) or reader in seen_readers or reader not in READERS:
            continue
        if not any(fnmatch.fnmatchcase(name, glob) for name in names for glob in (*row.manifests, *row.lockfiles)):
            continue
        seen_readers.add(reader)
        try:
            out.extend(READERS[reader](directory, Path(workspace) if workspace else None))
        except Exception:  # noqa: BLE001 - one unreadable lock leaves the rest
            continue
    return out


__all__ = ["READERS", "RESOLUTION_FILES", "Resolved", "SANDBOX_HOME", "resolved_in"]
