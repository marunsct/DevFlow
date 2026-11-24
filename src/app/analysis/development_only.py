"""Which resolved packages are for development only and do not ship (plan HK.6, LF.1300).

An advisory on a package that ships is a release gap; one on a test runner or a linter is not, because nothing the
product runs holds it. Each language says this in its own files, and one reader per kind is kept here beside the
lock-file readers (`app.analysis.resolved_packages`), named the same way:

- npm: the lock marks every package reached only through `devDependencies` with `"dev": true`;
- Composer: the lock keeps them under `packages-dev`;
- Python: names declared only in a development requirements file, a development or test extra, a dependency group, or
  Poetry's development group (and Poetry's older lock category `dev`);
- Cargo: `[dev-dependencies]` not also in `[dependencies]` or `[build-dependencies]`;
- Bundler: gems declared only in `development` or `test` groups;
- NuGet: a reference with `PrivateAssets` all, and every package of a test project.

What no file says - a Go module used only by tests, a package a development tool brings that the lock does not mark -
counts as shipped: the release then names it, rather than staying silent about something that ships.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DevelopmentOnly:
    """(ecosystem, name in lower case) of each package for development only; `everything` for a folder that holds a
    test project alone."""

    names: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    everything: frozenset[str] = field(default_factory=frozenset)

    def holds(self, ecosystem: str, name: str) -> bool:
        return ecosystem in self.everything or (ecosystem, _key(ecosystem, name)) in self.names


def _key(ecosystem: str, name: str) -> str:
    name = str(name or "").strip().lower()
    return re.sub(r"[-_.]+", "-", name) if ecosystem == "pypi" else name


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


def _npm(directory: Path) -> set[str]:
    lock = _json(directory / "package-lock.json")
    packages = lock.get("packages") if isinstance(lock, dict) else None
    found = set()
    for key, entry in (packages.items() if isinstance(packages, dict) else ()):
        if key and isinstance(entry, dict) and entry.get("dev") is True:
            found.add(str(entry.get("name") or key.rsplit("node_modules/", 1)[-1]).lower())
    return found


def _composer(directory: Path) -> set[str]:
    lock = _json(directory / "composer.lock")
    return {str(p["name"]).lower() for p in (lock.get("packages-dev") or [] if isinstance(lock, dict) else [])
            if isinstance(p, dict) and p.get("name")}


_A_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_DEVELOPMENT_FILES = ("requirements-dev*.txt", "requirements_dev*.txt", "dev-requirements*.txt",
                      "requirements-test*.txt", "requirements_test*.txt", "test-requirements*.txt")
_DEVELOPMENT_EXTRAS = {"dev", "develop", "development", "test", "tests", "testing", "lint", "docs", "typing"}


def _names(lines: list[str]) -> set[str]:
    out = set()
    for line in lines:
        line = str(line).split("#", 1)[0].strip()
        found = _A_REQUIREMENT.match(line)
        if found and not line.startswith("-"):
            out.add(_key("pypi", found.group(1)))
    return out


def _python(directory: Path) -> set[str]:
    development: set[str] = set()
    for glob in _DEVELOPMENT_FILES:
        for path in directory.glob(glob):
            development |= _names(_text(path).splitlines())
    shipped = _names(_text(directory / "requirements.txt").splitlines())
    manifest = _toml(directory / "pyproject.toml")
    project = manifest.get("project") or {}
    shipped |= _names(project.get("dependencies") or [])
    for extra, items in (project.get("optional-dependencies") or {}).items():
        (development if str(extra).lower() in _DEVELOPMENT_EXTRAS else shipped).update(_names(items or []))
    for items in (manifest.get("dependency-groups") or {}).values():
        development |= _names([i for i in items or [] if isinstance(i, str)])
    poetry = (manifest.get("tool") or {}).get("poetry") or {}
    shipped |= {_key("pypi", n) for n in (poetry.get("dependencies") or {}) if n.lower() != "python"}
    development |= {_key("pypi", n) for n in (poetry.get("dev-dependencies") or {})}
    for group, table in (poetry.get("group") or {}).items():
        if str(group).lower() != "main":
            development |= {_key("pypi", n) for n in ((table or {}).get("dependencies") or {})}
    for package in _toml(directory / "poetry.lock").get("package") or []:
        if isinstance(package, dict) and package.get("category") == "dev" and package.get("name"):
            development.add(_key("pypi", package["name"]))
    return development - shipped


def _cargo(directory: Path) -> set[str]:
    manifest = _toml(directory / "Cargo.toml")

    def names(table: object) -> set[str]:
        return {str(spec.get("package") or name).lower() if isinstance(spec, dict) else str(name).lower()
                for name, spec in (table.items() if isinstance(table, dict) else ())}

    return names(manifest.get("dev-dependencies")) - names(manifest.get("dependencies")) - names(
        manifest.get("build-dependencies"))


_A_GEM = re.compile(r"""^\s*gem\s+["']([^"']+)["']""")
_A_GROUP = re.compile(r"^\s*group\s+(.+?)\s+do\b")


def _bundler(directory: Path) -> set[str]:
    development, shipped = set(), set()
    groups: list[bool] = []
    for line in _text(directory / "Gemfile").splitlines():
        opened = _A_GROUP.match(line)
        if opened:
            named = set(re.findall(r":(\w+)|[\"'](\w+)[\"']", opened.group(1)))
            words = {a or b for a, b in named}
            groups.append(bool(words) and words <= {"development", "test"})
            continue
        if re.match(r"^\s*end\b", line) and groups:
            groups.pop()
            continue
        gem = _A_GEM.match(line)
        if gem:
            only_here = re.search(r"group:\s*\[?\s*:(?:development|test)\b", line)
            (development if (groups and groups[-1]) or only_here else shipped).add(gem.group(1).lower())
    return development - shipped


_A_REFERENCE = re.compile(r"<PackageReference\b([^>]*?)(?:/>|>(.*?)</PackageReference>)", re.I | re.S)


def _nuget(directory: Path) -> tuple[set[str], bool]:
    development: set[str] = set()
    projects = sorted(directory.glob("*.csproj")) + sorted(directory.glob("*.fsproj"))
    tests = 0
    for project in projects:
        text = _text(project)
        if re.search(r"<IsTestProject>\s*true\s*</IsTestProject>", text, re.I) or re.search(
                r"""Include\s*=\s*["']Microsoft\.NET\.Test\.Sdk["']""", text, re.I):
            tests += 1
        for attributes, inner in _A_REFERENCE.findall(text):
            name = re.search(r"""Include\s*=\s*["']([^"']+)["']""", attributes)
            private = re.search(r"""PrivateAssets\s*=\s*["']all["']""", attributes, re.I) or re.search(
                r"<PrivateAssets>\s*all\s*</PrivateAssets>", inner or "", re.I)
            if name and private:
                development.add(name.group(1).lower())
    return development, bool(projects) and tests == len(projects)


def development_only(directory: str | Path) -> DevelopmentOnly:
    """What in `directory`'s projects is for development only. Never raises."""
    directory = Path(directory)
    names: set[tuple[str, str]] = set()
    everything: set[str] = set()
    for ecosystem, reader in (("npm", _npm), ("packagist", _composer), ("pypi", _python), ("crates", _cargo),
                              ("rubygems", _bundler)):
        try:
            names |= {(ecosystem, _key(ecosystem, n)) for n in reader(directory)}
        except Exception:  # noqa: BLE001 - an unreadable file marks nothing
            continue
    try:
        found, a_test_project = _nuget(directory)
        names |= {("nuget", n) for n in found}
        if a_test_project:
            everything.add("nuget")
    except Exception:  # noqa: BLE001
        pass
    return DevelopmentOnly(frozenset(names), frozenset(everything))


__all__ = ["DevelopmentOnly", "development_only"]
