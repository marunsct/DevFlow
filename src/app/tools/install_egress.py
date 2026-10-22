"""Where an install may fetch from: the package registries and GitHub, nothing else (plan SF.1).

The `install` category is the one that runs with a network (`sandbox.NETWORK_CATEGORIES`),
and the grant had no limit on where: `pip install https://any.host/x.whl`, an
`--index-url` of a stranger's mirror, a `.npmrc` pointing the registry elsewhere,
or a `package.json` dependency given as a tarball URL all fetched and ran code
from wherever they named. Seeding already refuses a clone it cannot vouch for
before it fetches (`server.seeding`: the scheme, private hosts); this is the same
pattern for installs. Every host an install names - on its command line, or in the
manifest and configuration files the package manager reads from the directory it
runs in - must be a registry on `ALLOWED_HOSTS` or a subdomain of one. A host the
operator trusts is added with `INSTALL_ALLOWED_HOSTS` (comma-separated); `*` lifts
the check. An install that names no host goes to its manager's default registry,
which is on the list.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable, Sequence

#: The public package registries and source hosts, a subdomain of each included.
ALLOWED_HOSTS = frozenset({
    # JavaScript
    "registry.npmjs.org", "npmjs.org", "npmjs.com", "registry.yarnpkg.com", "yarnpkg.com", "jsr.io",
    # Python
    "pypi.org", "pythonhosted.org", "pypi.python.org",
    # Rust, Go, Ruby, PHP, .NET, JVM, Dart, Elixir, Swift/Obj-C
    "crates.io", "proxy.golang.org", "sum.golang.org", "golang.org", "go.dev", "rubygems.org",
    "packagist.org", "nuget.org", "repo.maven.apache.org", "repo1.maven.org", "maven.org",
    "plugins.gradle.org", "gradle.org", "pub.dev", "hex.pm", "cocoapods.org",
    # Source hosts packages are installed from
    "github.com", "githubusercontent.com", "gitlab.com", "bitbucket.org",
})

_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://)(?:[^@/\s\"']*@)?([A-Za-z0-9.-]+)", re.I)
#: `git@host:owner/repo`, the scp-like form git and the managers accept.
_SCP = re.compile(r"(?:^|[\s\"'+])[A-Za-z0-9_.-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}):")
#: Flags whose value is a registry or an index, in the managers that take them.
_HOST_FLAGS = frozenset({
    "--registry", "--index-url", "-i", "--extra-index-url", "--find-links", "-f", "--trusted-host",
    "--index", "--default-index", "--source", "-s",
})
#: Files a manager reads its registry or its dependencies from, in the directory it runs in.
_CONFIG_FILES = (".npmrc", ".yarnrc", ".yarnrc.yml", "bunfig.toml", "pip.conf", "pip.ini", "uv.toml",
                 ".pypirc", "pyproject.toml", "Pipfile", "Gemfile", "composer.json", "nuget.config")
_DEPENDENCY_KEYS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def allowed_hosts(environment: dict[str, str] | None = None) -> frozenset[str] | None:
    """The hosts installs may reach; None when the operator lifted the check (`*`)."""
    extra = (environment if environment is not None else os.environ).get("INSTALL_ALLOWED_HOSTS", "")
    names = {name.strip().lower() for name in extra.split(",") if name.strip()}
    if "*" in names:
        return None
    return ALLOWED_HOSTS | frozenset(names)


def _allowed(host: str, allowed: frozenset[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == name or host.endswith("." + name) for name in allowed)


def hosts_in(text: str) -> list[str]:
    """Every host a URL or an scp-like git address in `text` names, in order, once each."""
    found = [m.group(1) for m in _URL.finditer(text or "")] + [m.group(1) for m in _SCP.finditer(text or "")]
    return list(dict.fromkeys(host.lower().rstrip(".") for host in found if "." in host))


def _hosts_on_the_command_line(command: Sequence[str]) -> list[str]:
    words = [str(word) for word in command]
    found: list[str] = []
    for index, word in enumerate(words):
        found += hosts_in(word)
        flag, _, value = word.partition("=")
        if flag in _HOST_FLAGS:
            value = value or (words[index + 1] if index + 1 < len(words) else "")
            # `--trusted-host name` names a bare host, not a URL.
            found += hosts_in(value) or ([value.split(":")[0]] if "." in value and "/" not in value else [])
    return list(dict.fromkeys(host.lower() for host in found))


def _dependency_values(package_json: str) -> Iterable[str]:
    try:
        data = json.loads(package_json)
    except ValueError:
        return []
    values: list[str] = []
    for key in _DEPENDENCY_KEYS:
        section = data.get(key) if isinstance(data, dict) else None
        if isinstance(section, dict):
            values += [str(v) for v in section.values()]
    return values


def _hosts_in_the_files_read(directory: Path) -> list[tuple[str, str]]:
    """(host, the file naming it) for each host in the manifests and settings an install reads here."""
    found: list[tuple[str, str]] = []
    for name in _CONFIG_FILES:
        path = directory / name
        if path.is_file():
            found += [(host, name) for host in hosts_in(_read(path))]
    package = directory / "package.json"
    if package.is_file():
        for value in _dependency_values(_read(package)):
            found += [(host, "package.json") for host in hosts_in(value)]
    for path in sorted(directory.glob("requirements*.txt")):
        for line in _read(path).splitlines():
            if not line.strip().startswith("#"):
                found += [(host, path.name) for host in hosts_in(line)]
    return list(dict.fromkeys(found))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def refusal(command: Sequence[str], directory: str | Path | None,
            environment: dict[str, str] | None = None) -> str:
    """Why this install may not run - a host it names is not a registry - or ""."""
    allowed = allowed_hosts(environment)
    if allowed is None:
        return ""
    named = [(host, "the command") for host in _hosts_on_the_command_line(command)]
    if directory is not None and Path(directory).is_dir():
        named += _hosts_in_the_files_read(Path(directory))
    outside = [(host, where) for host, where in named if not _allowed(host, allowed)]
    if not outside:
        return ""
    listed = "; ".join(f"{host} (in {where})" for host, where in outside[:5])
    return (
        f"Not installing: this install would fetch from {listed}, which is not a package registry "
        "the harness lets an install reach. Install by name from the default registry "
        "(`npm install <package>`, `pip install <package>`), and keep registry and URL "
        "settings out of the project's files. The operator can allow a host with "
        "INSTALL_ALLOWED_HOSTS."
    )


__all__ = ["ALLOWED_HOSTS", "allowed_hosts", "hosts_in", "refusal"]
