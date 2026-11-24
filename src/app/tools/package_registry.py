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


def _fetch(url: str, most_bytes: int = MAX_RESPONSE_BYTES) -> tuple[int, bytes]:
    """(status, body) of a GET; the body stops one chunk past `most_bytes`, so a longer one says it is longer."""
    import httpx

    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                      headers={"User-Agent": "software-harness-package-lookup"}) as client:
        with client.stream("GET", url) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > most_bytes:
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


def _homes(*places: Any) -> list[str]:
    """A package's homepage and repository as URLs, as its registry gives them."""
    found: list[str] = []
    for place in places:
        if isinstance(place, dict):
            place = place.get("url")
        url = str(place or "").strip()
        url = re.sub(r"^git\+|\.git$", "", url).replace("git://", "https://").replace("ssh://git@", "https://")
        if url.startswith("github:"):
            url = "https://github.com/" + url[len("github:"):]
        if url.startswith(("http://", "https://")) and url not in found:
            found.append(url)
    return found[:4]


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
        "homes": _homes(data.get("homepage"), data.get("repository")),
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
        "homes": _homes(info.get("home_page"), *(info.get("project_urls") or {}).values()),
    }


def _numbers(text: Any) -> tuple[int, ...]:
    """The leading dotted number of a version or a runtime's banner: `rustc 1.85.1 (...)` is (1, 85, 1); () for none."""
    found = re.search(r"(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def _at_most(needed: Any, here: tuple[int, ...]) -> bool:
    """Whether a stated requirement (`1.82`, `1.89.0`) is met by this environment's version; True when either is unknown."""
    wanted = _numbers(needed)
    return not wanted or not here or wanted <= here[:len(wanted)] or wanted[:len(here)] < here


#: Why the version offered is not the newest: what the newest needs, which this environment does not have.
_NEWER_NEEDS_MORE = ("The newest release, {newest}, needs {needs}; this environment has {here}, so {version} is the "
                     "newest it builds - pin that.")


def _crates(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://crates.io/api/v1/crates/{quote(name)}")
    if status != 200:
        return {"status": status}
    data = _json(body)
    crate = data.get("crate") or {}
    version = crate.get("max_stable_version") or crate.get("newest_version")
    versions = [v for v in data.get("versions") or [] if isinstance(v, dict)]
    rust = next((v.get("rust_version") for v in versions if v.get("num") == version), None)
    found = {
        "version": version,
        "description": _short(crate.get("description")),
        "needs_runtime": {"rust": rust or "not stated"},
        "homes": _homes(crate.get("homepage"), crate.get("repository")),
    }
    # The newest release this environment's rustc builds (measured: `rusqlite` 0.43 needs rustc 1.89, the image has
    # 1.85, and the build failed in every round until a fixer pinned an older one).
    here = _numbers(runtime_here("crates"))
    if rust and here and not _at_most(rust, here):
        fits = next((v for v in versions if not v.get("yanked") and _is_stable(str(v.get("num") or ""))
                     and _at_most(v.get("rust_version"), here)), None)
        if fits and fits.get("num") != version:
            found.update(version=fits.get("num"), newest_release=version,
                         needs_runtime={"rust": fits.get("rust_version") or "not stated"},
                         note=_NEWER_NEEDS_MORE.format(newest=version, needs=f"rustc {rust}",
                                                       here=runtime_here("crates"), version=fits.get("num")))
    return found


def features_of(ecosystem: str, name: str, version: str = "", *, fetch: Fetch | None = None) -> list[str] | None:
    """The optional features a package version offers, sorted (`default` left out), or None when it cannot be read.

    Crates only for now: crates.io lists a version's features. Measured on four Rust runs: a manifest asked `rusqlite`
    for a `json` feature 0.37 does not have, cargo refused, and fixers guessed at it for rounds with no list to read.
    """
    if ecosystem != "crates" or not _A_NAME.match(name or ""):
        return None
    try:
        if not version:
            version = str(look_up("crates", name, fetch=fetch).get("version") or "")
        if not version:
            return None
        status, body = (fetch or _fetch)(f"https://crates.io/api/v1/crates/{quote(name)}/{quote(version)}")
        if status != 200:
            return None
        found = (_json(body).get("version") or {}).get("features")
        if not isinstance(found, dict):
            return None
        return sorted(key for key in found if key != "default")
    except Exception:  # noqa: BLE001 - an unreadable registry is no answer, not a crash
        logger.info("Could not read the features of %s %s", name, version)
        return None


def _go(name: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"https://proxy.golang.org/{_go_escaped(name)}/@latest")
    if status != 200:
        return {"status": status}
    return {"version": _json(body).get("Version"), "homes": _homes(f"https://{name}")}


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
    # A group is its publisher's domain reversed, and Maven Central checks it.
    return {"version": root.findtext("versioning/release") if not stable else stable[-1],
            "homes": _homes("https://" + ".".join(reversed(group.split(".")))) if group.count(".") >= 1 else []}


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
        "homes": _homes(data.get("homepage_uri"), data.get("source_code_uri")),
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
        "homes": _homes(latest.get("homepage"), (latest.get("source") or {}).get("url")),
    }


#: Releases of one NuGet package whose frameworks are read, newest first, before the newest is offered as it is.
MOST_NUGET_RELEASES_READ = 6
_A_FRAMEWORK = re.compile(r'targetFramework="([^"]+)"', re.I)


def _a_framework_this_sdk_runs(framework: str, here: tuple[int, ...]) -> bool:
    """Whether a package's target framework (`net8.0`, `.NETCoreApp8.0`, `netstandard2.0`) runs on this SDK's major."""
    name = framework.strip().lower()
    if "standard" in name or not here:
        return True
    major = _numbers(name)
    return bool(major) and major[0] <= here[0]


def _nuget_releases_to_read(stable: list[str]) -> list[str]:
    """The releases whose frameworks are read, in turn: the newest few, then the newest of each older major line.

    Measured on one run: `Microsoft.EntityFrameworkCore.Sqlite`'s six newest releases were 11.x and 10.x, all for a
    newer .NET than the SDK's 8; none fitted, the newest (11.0.0) was offered, and every restore failed NU1202 while a
    web lookup and two rewrites left it so. A platform package's major follows .NET's, so the release that fits is
    the newest of an older line, which reading only the newest few never reaches.
    """
    newest_first = list(reversed(stable))
    read = newest_first[:MOST_NUGET_RELEASES_READ]
    seen = {(_numbers(v) or (0,))[0] for v in read}
    for version in newest_first[MOST_NUGET_RELEASES_READ:]:
        major = (_numbers(version) or (0,))[0]
        if major not in seen:
            seen.add(major)
            read.append(version)
        if len(read) >= 2 * MOST_NUGET_RELEASES_READ:
            break
    return read


def _nuget(name: str, fetch: Fetch) -> dict[str, Any]:
    base = f"https://api.nuget.org/v3-flatcontainer/{quote(name.lower())}"
    status, body = fetch(f"{base}/index.json")
    if status != 200:
        return {"status": status}
    versions = [str(v) for v in _json(body).get("versions") or []]
    stable = [v for v in versions if _is_stable(v)]
    newest = (stable or versions or [None])[-1]
    # The newest release with a framework this SDK runs (measured: `Microsoft.Data.Sqlite` 11.0.0 targets net10.0
    # only, the image has .NET 8, and every restore failed NU1202). A release whose frameworks cannot be read, or
    # that names none, is taken as it is.
    here = _numbers(runtime_here("nuget"))
    for version in _nuget_releases_to_read(stable) if here else []:
        got, spec = fetch(f"{base}/{quote(version.lower())}/{quote(name.lower())}.nuspec")
        frameworks = _A_FRAMEWORK.findall(spec.decode("utf-8", "replace")) if got == 200 else []
        if not frameworks or any(_a_framework_this_sdk_runs(f, here) for f in frameworks):
            if version == newest:
                return {"version": newest}
            return {"version": version, "newest_release": newest,
                    "note": _NEWER_NEEDS_MORE.format(newest=newest, needs="a newer .NET than this SDK",
                                                     here=f".NET SDK {runtime_here('nuget')}", version=version)}
    return {"version": newest}


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

#: The answers that mean a registry has no package of that name: the Go proxy says 410 for a module it never had.
_NO_SUCH_PACKAGE = frozenset({404, 410})

_RUNTIMES: dict[str, str] = {}
_CACHE: dict[tuple[str, str, Any], dict[str, Any]] = {}


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
    # A name with the version asked for after it - `typescript@5`,
    # `fastapi==0.115`, `serde@1` - is the package; the registry answers with
    # its current release either way. One stage asked for `typescript@5` and
    # was told the registry had no such package.
    asked = re.match(r"^(@?[^@=<>!~^\s]+)(?:@|==|>=|<=|~=|!=|>|<|\^|~)[\w.*+^~-]*$", name)
    version_asked = ""
    if asked:
        version_asked = name[len(asked.group(1)):].lstrip("@=")
        name = asked.group(1)
    if not _A_NAME.match(name) or ".." in name:
        return {"error": f"{name!r} is not a package name."}
    # Keyed by where the answer came from as well: an answer read through a fetch the caller supplied is that fetch's
    # alone. Found when the dependency gate (LF.1074) began asking at every install: one stub's answer for a package
    # was handed to the next caller asking the same name through a stub of its own.
    key = (which, name, fetch)
    if key in _CACHE:
        return _with_the_version_asked(_CACHE[key], version_asked)
    from app.tools.outbound import refused_name  # the one outbound gate (HK.5): never the product's own name
    if refused := refused_name(which, name):
        return {"error": refused}
    try:
        found = _ECOSYSTEMS[which][1](name, fetch or _fetch)
    except Exception as exc:  # noqa: BLE001 - an unreachable registry is an answer, not a crash
        logger.info("Package lookup %s %s failed: %s", which, name, exc)
        return {"error": f"The {which} registry could not be read ({type(exc).__name__}); "
                         "go on with what the project already pins."}
    if found.get("status") in _NO_SUCH_PACKAGE and name != name.lower():
        # Asked by the name a person writes - `Hono`, `Playwright`,
        # `TypeScript` - where the registry's is lowercase. One run's research
        # found 1 of 7 libraries in its stack this way.
        lowered = look_up(which, name.lower() + (f"@{version_asked}" if version_asked else ""), fetch=fetch)
        if "error" not in lowered:
            return lowered
    if "status" in found:
        status = found["status"]
        if status in _NO_SUCH_PACKAGE:
            # `missing`: the registry's own answer that the name is not there, which the dependency gate refuses on.
            return {"error": f"The {which} registry has no package {name!r}.", "missing": True}
        return {"error": f"The {which} registry answered {status}; go on with what the project already pins."}
    if "error" in found:
        return found
    result = {"ecosystem": which, "package": name, **{k: v for k, v in found.items() if v not in (None, "", {}, [])}}
    result["this_environment_runs"] = runtime_here(which)
    _CACHE[key] = result
    return _with_the_version_asked(result, version_asked)


def _with_the_version_asked(result: dict[str, Any], version_asked: str) -> dict[str, Any]:
    """`result`, saying so when the current release is not the version asked for.

    So a stage that asked for one line of releases does not pin the current
    one thinking it is the line it asked for.
    """
    wanted = version_asked.lstrip("^~<>=!")
    if not wanted or str(result.get("version", "")).lstrip("v").startswith(wanted):
        return result
    return {**result, "note": f"{version_asked!r} was asked for; {result.get('version')} is the current "
                              "release, not one of those."}


def build_package_lookup_tool() -> Any:
    from langchain_core.tools import tool

    @tool
    def look_up_package(ecosystem: str, name: str) -> dict[str, Any]:
        """Ask a package registry for the current release of one or more packages.

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
                `laravel/framework`. Several at once, separated by commas -
                `hono, @hono/node-server, typescript` - in one call.
        """
        from app.tools.research import found, over_its_share

        names = [part.strip() for part in str(name or "").split(",") if part.strip()] or [str(name or "")]
        refusal = over_its_share("packages", len(names))
        if refusal:
            return {"error": refusal}
        answers = []
        for one in names:
            answer = look_up(ecosystem, one)
            found(f"look_up_package {ecosystem} {one}", answer)
            answers.append(answer)
        return answers[0] if len(answers) == 1 else {"packages": answers}

    return look_up_package


def lookup_tools() -> list[Any]:
    """The lookup as a list of tools, empty when it is switched off."""
    return [build_package_lookup_tool()] if enabled() else []
