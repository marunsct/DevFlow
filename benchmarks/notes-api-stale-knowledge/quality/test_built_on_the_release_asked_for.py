"""The product is built on the release line its brief asks for (bench.json's `asked_release`).

A stale-knowledge family asks for a framework whose current major line is newer than a model's training data and
renamed or removed what the older line had. A product that answers every request on the older line the model knows
did not do what the brief says, and its hidden score would hide that: this test reads the versions the product's own
manifests declare for the asked package and holds every one to the asked major. The scorer gives the benchmark's
folder as `BENCH_DIR` and the product's as `PRODUCT_DIR`.

Readers: Maven (`pom.xml`: a parent, an imported bill of materials, a plugin or a dependency of the package's group,
`${property}` versions resolved from the POM's properties), Gradle (`build.gradle`, `build.gradle.kts`: the plugin
id or a `group:artifact:version` coordinate), npm (`package.json`, the installed copy's version first) and PyPI
(`requirements*.txt`, `pyproject.toml`). A family asking for another ecosystem adds its reader here.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: Folders that hold no manifest of the product's own.
_NOT_THE_PRODUCT_S = {"node_modules", ".venv", "venv", "target", "build", "dist", ".git", ".gradle", ".mvn"}


def _manifests(product: Path, *names: str) -> list[Path]:
    return sorted(path for name in names for path in product.rglob(name)
                  if not set(path.relative_to(product).parts[:-1]) & _NOT_THE_PRODUCT_S)


def _maven(product: Path, group: str) -> list[str]:
    found = []
    for pom in _manifests(product, "pom.xml"):
        text = re.sub(r"<!--.*?-->", "", pom.read_text(encoding="utf-8", errors="replace"), flags=re.S)
        properties = dict(re.findall(r"<([\w.-]+)>\s*([^<\s][^<]*?)\s*</\1>",
                                     "".join(re.findall(r"<properties>(.*?)</properties>", text, re.S))))
        for block in re.findall(r"<(?:parent|dependency|plugin)>(.*?)</(?:parent|dependency|plugin)>", text, re.S):
            if re.search(rf"<groupId>\s*{re.escape(group)}\s*</groupId>", block):
                version = re.search(r"<version>\s*([^<]+?)\s*</version>", block)
                if version:
                    said = version.group(1)
                    named = re.fullmatch(r"\$\{([\w.-]+)\}", said)
                    found.append(properties.get(named.group(1), said) if named else said)
    return found


def _gradle(product: Path, group: str) -> list[str]:
    found = []
    for build in _manifests(product, "build.gradle", "build.gradle.kts"):
        text = build.read_text(encoding="utf-8", errors="replace")
        found += re.findall(rf"""id\s*\(?\s*["']{re.escape(group)}["']\s*\)?\s*version\s*["']([^"']+)["']""", text)
        found += re.findall(rf"""["']{re.escape(group)}:[\w.-]+:([^"':]+)["']""", text)
    return found


def _npm(product: Path, package: str) -> list[str]:
    found = []
    for manifest in _manifests(product, "package.json"):
        installed = manifest.parent / "node_modules" / package / "package.json"
        try:
            found.append(json.loads(installed.read_text(encoding="utf-8"))["version"])
            continue
        except (OSError, ValueError, KeyError):
            pass
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for field in ("dependencies", "devDependencies"):
            said = (data.get(field) or {}).get(package)
            if said:
                found.append(said)
    return found


def _pypi(product: Path, package: str) -> list[str]:
    name = re.escape(package).replace(r"\-", "[-_.]").replace("_", "[-_.]")
    found = []
    for manifest in _manifests(product, "requirements*.txt", "pyproject.toml"):
        text = manifest.read_text(encoding="utf-8", errors="replace")
        found += re.findall(rf"""(?im)^\s*["']?{name}(?:\[[^\]]*\])?\s*(?:==|>=|~=|\^|>)\s*([\d][\w.]*)""", text)
    return found


READERS = {"maven": lambda product, package: _maven(product, package) + _gradle(product, package),
           "npm": _npm, "pypi": _pypi}


def declared_versions(product: Path, ecosystem: str, package: str) -> list[str]:
    """The versions the product's manifests declare for `package`, as written (a range keeps its operator)."""
    return READERS[ecosystem](Path(product), package)


def off_the_line(versions: list[str], major: str) -> list[str]:
    """The declared versions that are not on the asked major line."""
    return [v for v in versions if (re.search(r"\d+", v) or [None])[0] != str(major)]


def test_the_product_is_built_on_the_release_line_its_brief_asks_for():
    asked = json.loads((Path(os.environ["BENCH_DIR"]) / "bench.json").read_text(encoding="utf-8"))["asked_release"]

    versions = declared_versions(Path(os.environ["PRODUCT_DIR"]), asked["ecosystem"], asked["package"])

    assert versions, f"no manifest of the product declares {asked['package']}"
    assert off_the_line(versions, asked["major"]) == [], (
        f"{asked['framework']} {asked['major']} was asked for; the product declares {versions}")
