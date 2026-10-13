"""What a package registry says about a package today.

A local model's knowledge of a framework stops at its training data. Measured
on this harness: Angular 22 needs Node 22.22 or later and Node 24 stopped
taking a directory for `node --test` - both after the model served here was
trained, and both cost a run before anything said so. A stage that picks or
pins a version has had no way to ask what is current.

This asks the registry each ecosystem installs from, and nothing else: no
search engine, no arbitrary address. The host is fixed per ecosystem and the
name is checked before it is put in a path, so a brief cannot point a stage at
a page of its choosing, and what comes back is facts a registry publishes - a
version, the runtime it needs, its peer dependencies - with the free text cut
short. Beside them, the version of the runtime this environment has, so a
stage can see a mismatch before an install does.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from typing import Any, Callable
from urllib.parse import quote

logger = logging.getLogger(__name__)

#: Seconds one registry request may take.
TIMEOUT_SECONDS = float(os.environ.get("PACKAGE_LOOKUP_TIMEOUT", "10"))
#: The most of one response read. PyPI's and Packagist's documents for a large
#: project run to a megabyte; anything past this is not a registry answer.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
#: The longest free text (a description) passed on.
MAX_TEXT = 300
#: The most dependencies listed for one package.
MAX_LISTED = 20

#: A package name as any of these registries spells one, and nothing that could
#: leave its path: no "..", no whitespace, no query or fragment.
_A_NAME = re.compile(r"^[@A-Za-z0-9][@A-Za-z0-9._/:~+-]{0,213}$")

#: Fetches a URL and returns (status, body). Injected so tests need no network.
Fetch = Callable[[str], tuple[int, bytes]]


def enabled() -> bool:
    """Whether stages are given the lookup (`PACKAGE_LOOKUP_ENABLED`, on by default)."""
    return os.environ.get("PACKAGE_LOOKUP_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _fetch(url: str) -> tuple[int, bytes]:
    import httpx

    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                      headers={"User-Agent": "software-harness-package-lookup"}) as client:
        with client.stream("GET", url) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    break
            return response.status_code, bytes(body)


def _short(text: Any) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _listed(items: Any) -> list[str] | dict[str, str]:
    if isinstance(items, dict):
        return {str(k): str(v) for k, v in list(items.items())[:MAX_LISTED]}
    return [str(item) for item in list(items or [])[:MAX_LISTED]]


def _json(body: bytes) -> Any:
    import json

    return json.loads(body.decode("utf-8"))


def _go_escaped(module: str) -> str:
    """A module path as the Go proxy spells it: each capital as "!" and its lower case."""
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module)


def _is_stable(version: str) -> bool:
    return not re.search(r"[-+]|alpha|beta|rc|preview|snapshot|dev", version, re.I)


# --- one reader per registry ----------------------------------------------------

def _npm(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://registry.npmjs.org/{name}/latest")
    if status != 200:
        return {"status": status}
    data = _json(body)
    return {
        "version": data.get("version"),
        "description": _short(data.get("description")),
        "needs_runtime": _listed(data.get("engines") or {}),
        "peer_dependencies": _listed(data.get("peerDependencies") or {}),
        "module_type": data.get("type") or "commonjs",
    }


def _pypi(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://pypi.org/pypi/{quote(name)}/json")
    if status != 200:
        return {"status": status}
    info = _json(body).get("info") or {}
    return {
        "version": info.get("version"),
        "description": _short(info.get("summary")),
        "needs_runtime": {"python": info.get("requires_python") or "any"},
        "dependencies": _listed(
            [d for d in (info.get("requires_dist") or []) if "extra ==" not in str(d)]
        ),
    }


def _crates(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://crates.io/api/v1/crates/{quote(name)}")
    if status != 200:
        return {"status": status}
    data = _json(body)
    crate = data.get("crate") or {}
    version = crate.get("max_stable_version") or crate.get("newest_version")
    rust = next(
        (v.get("rust_version") for v in data.get("versions") or [] if v.get("num") == version), None
    )
    return {
        "version": version,
        "description": _short(crate.get("description")),
        "needs_runtime": {"rust": rust or "not stated"},
    }


def _go(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://proxy.golang.org/{_go_escaped(name)}/@latest")
    if status != 200:
        return {"status": status}
    return {"version": _json(body).get("Version")}


def _maven(name: str, fetch: Fetch) -> dict[str, Any]:
    group, _, artifact = name.partition(":")
    if not group or not artifact or ":" in artifact:
        return {"error": "A Maven package is named `group:artifact`, e.g. `io.ktor:ktor-server-core-jvm`."}
    status, body = fetch(
        f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
    )
    if status != 200:
        return {"status": status}
    root = ElementTree.fromstring(body)
    versions = [v.text or "" for v in root.iter("version")]
    stable = [v for v in versions if _is_stable(v)]
    return {"version": root.findtext("versioning/release") if not stable else stable[-1]}


def _rubygems(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://rubygems.org/api/v1/gems/{quote(name)}.json")
    if status != 200:
        return {"status": status}
    data = _json(body)
    return {
        "version": data.get("version"),
        "description": _short(data.get("info")),
        "dependencies": _listed(
            [f"{d.get('name')} {d.get('requirements')}" for d in (data.get("dependencies") or {}).get("runtime") or []]
        ),
    }


def _packagist(name: str, fetch: Fetch) -> dict[str, Any]:
    if name.count("/") != 1:
        return {"error": "A Composer package is named `vendor/name`, e.g. `laravel/framework`."}
    status, body = fetch(f"https://repo.packagist.org/p2/{name.lower()}.json")
    if status != 200:
        return {"status": status}
    releases = (_json(body).get("packages") or {}).get(name.lower()) or []
    latest = next((r for r in releases if _is_stable(str(r.get("version", "")))), releases[0] if releases else {})
    requires = latest.get("require") or {}
    return {
        "version": latest.get("version"),
        "description": _short(latest.get("description")),
        "needs_runtime": {"php": requires.get("php", "not stated")} if isinstance(requires, dict) else {},
    }


def _nuget(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://api.nuget.org/v3-flatcontainer/{quote(name.lower())}/index.json")
    if status != 200:
        return {"status": status}
    versions = [str(v) for v in _json(body).get("versions") or []]
    stable = [v for v in versions if _is_stable(v)]
    return {"version": (stable or versions or [None])[-1]}


#: Each ecosystem: the words that name it, how to read its registry, and the
#: command that reports this environment's runtime for it.
_ECOSYSTEMS: dict[str, tuple[tuple[str, ...], Callable[[str, Fetch], dict[str, Any]], tuple[str, ...]]] = {
    "npm": (("npm", "node", "javascript", "typescript", "js", "ts", "yarn", "pnpm"), _npm, ("node", "--version")),
    "pypi": (("pypi", "pip", "python", "py"), _pypi, ("python3", "--version")),
    "crates": (("crates", "cargo", "rust", "crates.io"), _crates, ("rustc", "--version")),
    "go": (("go", "golang", "gomod"), _go, ("go", "version")),
    "maven": (("maven", "gradle", "java", "kotlin", "jvm"), _maven, ("java", "-version")),
    "rubygems": (("rubygems", "gem", "ruby", "bundler"), _rubygems, ("ruby", "--version")),
    "packagist": (("packagist", "composer", "php"), _packagist, ("php", "--version")),
    "nuget": (("nuget", "dotnet", ".net", "csharp", "c#"), _nuget, ("dotnet", "--version")),
}

_RUNTIMES: dict[str, str] = {}
_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def ecosystem_named(word: str) -> str | None:
    word = str(word or "").strip().lower()
    for ecosystem, (names, _, _) in _ECOSYSTEMS.items():
        if word == ecosystem or word in names:
            return ecosystem
    return None


def runtime_here(ecosystem: str) -> str:
    """The version of the runtime this environment has for `ecosystem`, or "not installed"."""
    if ecosystem in _RUNTIMES:
        return _RUNTIMES[ecosystem]
    argv = _ECOSYSTEMS[ecosystem][2]
    found = "not installed"
    if shutil.which(argv[0]):
        try:
            done = subprocess.run(list(argv), capture_output=True, text=True, timeout=20, check=False)
            text = (done.stdout or done.stderr).strip().splitlines()
            found = text[0][:120] if text else "installed, version unknown"
        except (OSError, subprocess.SubprocessError):
            found = "installed, version unknown"
    _RUNTIMES[ecosystem] = found
    return found


def look_up(ecosystem: str, name: str, *, fetch: Fetch | None = None) -> dict[str, Any]:
    """The registry's current release of `name`, or {"error": ...} saying why there is none."""
    which = ecosystem_named(ecosystem)
    if which is None:
        return {"error": f"Unknown ecosystem {ecosystem!r}; use one of: {', '.join(_ECOSYSTEMS)}."}
    name = str(name or "").strip()
    if not _A_NAME.match(name) or ".." in name:
        return {"error": f"{name!r} is not a package name."}
    key = (which, name)
    if key in _CACHE:
        return _CACHE[key]
    try:
        found = _ECOSYSTEMS[which][1](name, fetch or _fetch)
    except Exception as exc:  # noqa: BLE001 - an unreachable registry is an answer, not a crash
        logger.info("Package lookup %s %s failed: %s", which, name, exc)
        return {"error": f"The {which} registry could not be read ({type(exc).__name__}); "
                         "go on with what the project already pins."}
    if "status" in found:
        status = found["status"]
        return {"error": f"The {which} registry has no package {name!r}." if status == 404
                else f"The {which} registry answered {status}; go on with what the project already pins."}
    if "error" in found:
        return found
    result = {"ecosystem": which, "package": name, **{k: v for k, v in found.items() if v not in (None, "", {}, [])}}
    result["this_environment_runs"] = runtime_here(which)
    _CACHE[key] = result
    return result


def build_package_lookup_tool() -> Any:
    from langchain_core.tools import tool

    @tool
    def look_up_package(ecosystem: str, name: str) -> dict[str, Any]:
        """Ask a package registry for the current release of one package.

        Returns its latest stable version, the runtime version it needs, its
        peer dependencies where the registry lists them, and the version of
        that runtime this environment has. Use it before choosing or pinning a
        version you are not sure of: what you remember may be older than the
        registry. Reads the official registry only.

        Args:
            ecosystem: npm, pypi, crates, go, maven, rubygems, packagist or nuget
                (a language name such as python or rust works too).
            name: the package as that registry names it - `@angular/core`,
                `fastapi`, `github.com/gin-gonic/gin`, `io.ktor:ktor-server-core-jvm`,
                `laravel/framework`.
        """
        return look_up(ecosystem, name)

    return look_up_package


def lookup_tools() -> list[Any]:
    """The lookup as a list of tools, empty when it is switched off."""
    return [build_package_lookup_tool()] if enabled() else []
