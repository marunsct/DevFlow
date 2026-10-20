"""The packages a project's manifests declare, in every ecosystem the harness knows.

One reader for each manifest - `package.json`, `pyproject.toml` and the
requirements files, `go.mod`, `Cargo.toml`, `pom.xml`, `composer.json`,
`Gemfile`, `.csproj` - shared by the loop's pack-freshness check and by the
search for a library's official MCP server (`app.tools.mcp_registry`), so a
language one of them reads the other reads too.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

#: Manifest file names, and the suffix a .NET project file ends in.
MANIFEST_NAMES = frozenset({
    "package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt", "go.mod", "Cargo.toml",
    "pom.xml", "composer.json", "Gemfile",
})


def pins(files: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """(file, ecosystem, package, pinned version) for every version the files pin."""
    found: list[tuple[str, str, str, str]] = []
    for name, text in files.items():
        base = name.rsplit("/", 1)[-1]
        try:
            if base == "package.json":
                data = json.loads(text)
                for section in ("dependencies", "devDependencies"):
                    for package, version in (data.get(section) or {}).items():
                        if re.match(r"^[\^~]?\d", str(version)):
                            found.append((name, "npm", package, version))
            elif base in {"pyproject.toml", "requirements.txt", "requirements-dev.txt"}:
                for package, version in re.findall(r'"?([A-Za-z0-9_.\-\[\]]+?)(?:\[[^\]]*\])?\s*(?:>=|==|~=)\s*([0-9][0-9.]*)', text):
                    found.append((name, "pypi", package.split("[")[0], version))
            elif base == "go.mod":
                for package, version in re.findall(r"^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/[^\s]+)\s+(v[0-9][^\s]*)", text, re.M):
                    found.append((name, "go", package, version))
            elif base == "Cargo.toml":
                # Only the dependency tables: `[package]` has a `version` of its own.
                text = "\n".join(re.findall(r"(?ms)^\[(?:dev-|build-)?dependencies\]\n(.*?)(?=^\[|\Z)", text))
                for package, plain, table in re.findall(r'^([a-z0-9_\-]+)\s*=\s*(?:"([0-9][^"]*)"|\{[^}]*version\s*=\s*"([0-9][^"]*)")', text, re.M):
                    found.append((name, "crates", package, plain or table))
            elif base == "pom.xml":
                root = ElementTree.fromstring(re.sub(r'\sxmlns="[^"]+"', "", text, count=1))
                for element in [root.find("parent"), *root.iter("dependency")]:
                    if element is None:
                        continue
                    group, artifact, version = (element.findtext(k) or "" for k in ("groupId", "artifactId", "version"))
                    if group and artifact and re.match(r"^\d", version):
                        found.append((name, "maven", f"{group}:{artifact}", version))
            elif base == "composer.json":
                for package, version in (json.loads(text).get("require") or {}).items():
                    if "/" in package and re.search(r"\d", version):
                        found.append((name, "packagist", package, version))
            elif base == "Gemfile":
                for package, version in re.findall(r'^\s*gem\s+"([^"]+)",\s*"[~><=\s]*([0-9][^"]*)"', text, re.M):
                    found.append((name, "rubygems", package, version))
            elif base.endswith(".csproj"):
                for package, version in re.findall(r'PackageReference Include="([^"]+)" Version="([^"]+)"', text):
                    found.append((name, "nuget", package, version))
        except (ValueError, ElementTree.ParseError):
            continue
    return [(f, e, p, v) for f, e, p, v in found if v]


def in_the_project(root: str | Path, *, most_files: int = 40) -> list[tuple[str, str, str, str]]:
    """`pins` of the manifests under `root`, skipping the folders a tool fills."""
    import os

    from app.tools.repository import INSTALLED_DIRECTORIES

    base = Path(root)
    files: dict[str, str] = {}
    for directory, folders, names in os.walk(base):
        folders[:] = [f for f in folders if f not in INSTALLED_DIRECTORIES and not f.startswith(".")]
        for name in names:
            if name in MANIFEST_NAMES or name.endswith(".csproj"):
                path = Path(directory, name)
                try:
                    files[path.relative_to(base).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
        if len(files) >= most_files:
            break
    return pins(files)


__all__ = ["MANIFEST_NAMES", "in_the_project", "pins"]
