"""Which release of a package this environment's toolchain runs, read from each registry's own field (HK.1, LF.1292).

A registry's newest release can need a newer runtime than the one here. Measured: a Rust run never built because
crates needed rustc 1.86-1.88 under the image's 1.85 (0 of 9 hidden tests in four runs); a C# run restored a package
that targets net10.0 only under .NET 8 and failed NU1202 every round. The crates and NuGet readers of
`package_registry` already offered the newest release that fits; npm read `/latest` alone, PyPI the newest version
alone, and no reader but crates said a release was yanked or deprecated.

Here every registry is read the same way: each release with its date, the runtime it says it needs, and whether it was
withdrawn (yanked, deprecated, unlisted); the newest stable release whose stated need this environment meets is the one
offered. Each registry's own field is read: npm `engines.node`, PyPI `requires_python`, crates `rust_version`, Go the
module's `go` directive, RubyGems `ruby_version`, Packagist `require.php`, NuGet the target frameworks. Maven states no
runtime a release needs, so it is offered as the registry has it.

Only registry hosts are asked, through `package_registry`'s fetch, so whatever gates that fetch gates these reads too.
A requirement that cannot be read, or a toolchain that is not installed, counts as fitting: a release is never held
back on a guess.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

logger = logging.getLogger(__name__)

#: Fetches a URL and returns (status, body), as `package_registry.Fetch`.
Fetch = Callable[[str], tuple[int, bytes]]

#: Releases whose stated need is read one request each (Go modules, NuGet packages), newest first, before giving up.
MOST_RELEASES_READ_ONE_BY_ONE = 8

#: The runtime each registry's requirement is about, as a person names it.
RUNTIME_OF = {
    "npm": "node", "pypi": "python", "crates": "rustc", "go": "go", "maven": "java", "rubygems": "ruby",
    "packagist": "php", "nuget": ".NET SDK",
}
#: The runtime `app.tools.runtimes` pins for a project, by ecosystem: a pinned one is the toolchain its commands use.
_PINNED_AS = {"npm": "node", "pypi": "python", "go": "go", "maven": "java"}


@dataclass(frozen=True)
class Release:
    """One release as its registry describes it."""

    version: str
    #: The day it was published (YYYY-MM-DD), "" when the registry does not say in the read made.
    released: str = ""
    #: The runtime it needs as its registry states it; "" when it states none; None when not read yet.
    needs: str | None = None
    #: Why it should not be chosen: "yanked", "deprecated: ...", "unlisted"; "" for none.
    withdrawn: str = ""


def _fetch_default() -> Fetch:
    from app.tools import package_registry

    return package_registry._fetch  # noqa: SLF001 - the one registry fetch, so whatever gates it gates these reads


def _json(body: bytes) -> Any:
    import json

    return json.loads(body.decode("utf-8"))


def _day(text: Any) -> str:
    found = re.match(r"\d{4}-\d{2}-\d{2}", str(text or ""))
    return found.group(0) if found else ""


def numbers(text: Any) -> tuple[int, ...]:
    """The leading dotted number of a version or a runtime's banner: `go version go1.26.9 linux` is (1, 26, 9)."""
    found = re.search(r"(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def is_stable(version: str) -> bool:
    return bool(version) and not re.search(r"[-+]|alpha|beta|rc|preview|snapshot|dev|a\d|b\d", version, re.I)


def _newest_first(releases: list[Release]) -> list[Release]:
    return sorted(releases, key=lambda r: numbers(r.version), reverse=True)


# --- what a stated requirement allows -----------------------------------------------------------------------------

_COMPARATOR = re.compile(
    r"(?P<op>>=|<=|!=|===|==|~=|~>|\^|~|>|<|=)?\s*v?(?P<version>(?:\d+|[xX*])(?:\.(?:\d+|[xX*]))*)(?:[-+][0-9A-Za-z.-]*)?"
)


def _compare(here: tuple[int, ...], wanted: tuple[int, ...]) -> tuple[int, bool]:
    """(-1, 0 or 1 for here against wanted, whether wanted was cut to here's precision): a toolchain known to fewer
    places than a bound is equal to it at those places, never wrongly below it."""
    cut = len(wanted) > len(here)
    padded = tuple(wanted[: len(here)]) if cut else tuple(wanted) + (0,) * (len(here) - len(wanted))
    return (here > padded) - (here < padded), cut


def _below(here: tuple[int, ...], bound: tuple[int, ...]) -> bool:
    order, cut = _compare(here, bound)
    return order < 0 or (order == 0 and cut)


def _one(op: str, version: str, here: tuple[int, ...], npm_tilde: bool) -> bool:
    parts = version.split(".")
    wildcard = any(p.lower() in {"x", "*"} for p in parts)
    wanted = tuple(int(p) for p in parts if p.isdigit()) if not wildcard else tuple(
        int(p) for p in parts[: next(i for i, p in enumerate(parts) if not p.isdigit())])
    if not wanted:
        return True  # `*`, `x`: anything
    order, cut = _compare(here, wanted)
    prefix = here[: len(wanted)] == wanted[: len(here)]
    if op in ("", "=", "==", "==="):
        return prefix if (wildcard or len(wanted) <= len(here)) else order == 0
    if op == "!=":
        return not (prefix if (wildcard or len(wanted) <= len(here)) else order == 0)
    if op == ">=":
        return order >= 0
    if op == ">":
        return order > 0 or (order == 0 and cut)
    if op == "<":
        return _below(here, wanted)
    if op == "<=":
        return order <= 0
    if order < 0:
        return False  # every caret and tilde form is at least the version it names
    if op == "^":
        at = next((i for i, part in enumerate(wanted) if part), len(wanted) - 1)
        return _below(here, wanted[:at] + (wanted[at] + 1,))
    if op == "~" and npm_tilde:
        return _below(here, (wanted[0], wanted[1] + 1) if len(wanted) >= 2 else (wanted[0] + 1,))
    # `~>` (RubyGems), `~=` (PEP 440) and Composer's `~`: the next-to-last place may grow.
    return _below(here, wanted[:-2] + (wanted[-2] + 1,) if len(wanted) >= 2 else (wanted[0] + 1,))


def satisfies(requirement: str, here: tuple[int, ...], *, npm_tilde: bool = False) -> bool | None:
    """Whether a runtime at `here` meets a stated requirement (`>=18`, `^8.1 || ^8.2`, `>=3.9,<3.13`, `>= 2.7.0`,
    `~> 3.1`); None when it cannot be read. `npm_tilde`: `~1.2` allows 1.2.x only, as npm reads it."""
    text = str(requirement or "").strip()
    if not text or not here:
        return None
    readable = False
    for alternative in re.split(r"\|\|?", text):
        alternative = re.sub(r"(\S+)\s+-\s+(\S+)", r">=\1 <=\2", alternative.strip())
        if not alternative:
            continue
        leftover = _COMPARATOR.sub(" ", alternative)
        if re.search(r"[A-Za-z0-9]", leftover):
            continue  # not a requirement this reads
        comparators = list(_COMPARATOR.finditer(alternative))
        if not comparators:
            continue
        readable = True
        if all(_one(m.group("op") or "", m.group("version"), here, npm_tilde) for m in comparators):
            return True
    return False if readable else None


def _a_framework_this_sdk_runs(framework: str, here: tuple[int, ...]) -> bool:
    """`net8.0`, `.NETCoreApp8.0`, `netstandard2.0`: a .NET Standard one runs anywhere; else its major is at most the
    SDK's."""
    name = framework.strip().lower()
    if not name or "standard" in name or not here:
        return True
    if re.match(r"^net\d{2,3}$", name) or name.startswith("net4") or "framework" in name:
        return False  # the old .NET Framework (net48, net472): Windows-only
    major = numbers(name)
    return bool(major) and major[0] <= here[0]


def fits(ecosystem: str, needs: str | None, here: str | tuple[int, ...]) -> bool:
    """Whether a release stating `needs` runs on the toolchain `here` (its banner or its numbers). True when either is
    unknown: a release is never held back on a guess."""
    version = here if isinstance(here, tuple) else numbers(here)
    if not needs or not version:
        return True
    if ecosystem == "nuget":
        frameworks = [f for f in re.split(r"[;,\s]+", needs) if f]
        return not frameworks or any(_a_framework_this_sdk_runs(f, version) for f in frameworks)
    if ecosystem in ("crates", "go"):
        return satisfies(f">={needs}", version) is not False
    return satisfies(needs, version, npm_tilde=ecosystem == "npm") is not False


# --- each registry's releases -------------------------------------------------------------------------------------

def _npm(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://registry.npmjs.org/{name}")
    if status != 200:
        return []
    data = _json(body)
    times = data.get("time") or {}
    found = []
    for version, document in (data.get("versions") or {}).items():
        document = document if isinstance(document, dict) else {}
        engines = document.get("engines")
        needs = str(engines.get("node") or "") if isinstance(engines, dict) else ""
        deprecated = document.get("deprecated")
        found.append(Release(version, _day(times.get(version)), needs,
                             f"deprecated: {str(deprecated)[:160]}" if deprecated else ""))
    return found


def _pypi(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://pypi.org/pypi/{quote(name)}/json")
    if status != 200:
        return []
    found = []
    for version, files in (_json(body).get("releases") or {}).items():
        files = [f for f in files or [] if isinstance(f, dict)]
        if not files:
            continue
        needs = next((str(f.get("requires_python")) for f in files if f.get("requires_python")), "")
        yanked = all(f.get("yanked") for f in files)
        found.append(Release(version, min((_day(f.get("upload_time_iso_8601") or f.get("upload_time")) for f in files),
                                          default=""),
                             needs, "yanked" if yanked else ""))
    return found


def _crates(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://crates.io/api/v1/crates/{quote(name)}")
    if status != 200:
        return []
    return [Release(str(v.get("num") or ""), _day(v.get("created_at")), str(v.get("rust_version") or ""),
                    "yanked" if v.get("yanked") else "")
            for v in _json(body).get("versions") or [] if isinstance(v, dict) and v.get("num")]


def _rubygems(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://rubygems.org/api/v1/versions/{quote(name)}.json")
    if status != 200:
        return []
    found: dict[str, Release] = {}
    for v in _json(body) or []:
        if not isinstance(v, dict) or not v.get("number"):
            continue
        number = str(v["number"])
        # One entry per platform: the plain one (`ruby`) speaks for the release.
        if number in found and str(v.get("platform") or "ruby") != "ruby":
            continue
        found[number] = Release(number, _day(v.get("created_at")), str(v.get("ruby_version") or ""),
                                "" if not v.get("yanked") else "yanked")
    return list(found.values())


def _expanded(entries: list[Any]) -> list[dict[str, Any]]:
    """Packagist's minified release list: each entry holds only what changed from the one before it."""
    out: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        current = dict(last)
        for key, value in entry.items():
            if value == "__unset":
                current.pop(key, None)
            else:
                current[key] = value
        out.append(current)
        last = current
    return out


def _packagist(name: str, fetch: Fetch) -> list[Release]:
    if name.count("/") != 1:
        return []
    status, body = fetch(f"https://repo.packagist.org/p2/{name.lower()}.json")
    if status != 200:
        return []
    found = []
    for entry in _expanded((_json(body).get("packages") or {}).get(name.lower()) or []):
        requires = entry.get("require") if isinstance(entry.get("require"), dict) else {}
        abandoned = entry.get("abandoned")
        found.append(Release(str(entry.get("version") or "").lstrip("v"), _day(entry.get("time")),
                             str(requires.get("php") or ""),
                             (f"abandoned{f': use {abandoned}' if isinstance(abandoned, str) else ''}"
                              if abandoned else "")))
    return [r for r in found if r.version]


def _go_escaped(module: str) -> str:
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module)


def _go(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://proxy.golang.org/{_go_escaped(name)}/@v/list")
    if status != 200:
        return []
    return [Release(line.strip()) for line in body.decode("utf-8", "replace").splitlines() if line.strip()]


def _go_needs(name: str, version: str, fetch: Fetch) -> tuple[str, str]:
    """(the module's `go` directive, a deprecation) from its go.mod at `version`."""
    status, body = fetch(f"https://proxy.golang.org/{_go_escaped(name)}/@v/{quote(version)}.mod")
    if status != 200:
        return "", ""
    text = body.decode("utf-8", "replace")
    directive = re.search(r"^go\s+(\d+(?:\.\d+)*)", text, re.M)
    deprecated = re.search(r"//\s*Deprecated:\s*(.+)", text)
    return (directive.group(1) if directive else "",
            f"deprecated: {deprecated.group(1).strip()[:160]}" if deprecated else "")


_A_FRAMEWORK = re.compile(r'targetFramework="([^"]+)"', re.I)


def _nuget(name: str, fetch: Fetch) -> list[Release]:
    status, body = fetch(f"https://api.nuget.org/v3-flatcontainer/{quote(name.lower())}/index.json")
    if status != 200:
        return []
    return [Release(str(v)) for v in _json(body).get("versions") or []]


def _nuget_needs(name: str, version: str, fetch: Fetch) -> str:
    base = f"https://api.nuget.org/v3-flatcontainer/{quote(name.lower())}"
    status, body = fetch(f"{base}/{quote(version.lower())}/{quote(name.lower())}.nuspec")
    if status != 200:
        return ""
    return ";".join(dict.fromkeys(_A_FRAMEWORK.findall(body.decode("utf-8", "replace"))))


def _nuget_published(name: str, version: str, fetch: Fetch) -> tuple[str, str]:
    """(the day a NuGet release was published, "unlisted" when it is): one registration read."""
    status, body = fetch(f"https://api.nuget.org/v3/registration5-semver1/{quote(name.lower())}/{quote(version.lower())}.json")
    if status != 200:
        return "", ""
    data = _json(body)
    day = _day(data.get("published"))
    return ("" if day.startswith("1900") else day), ("unlisted" if data.get("listed") is False else "")


def _maven(name: str, fetch: Fetch) -> list[Release]:
    import xml.etree.ElementTree as ElementTree

    group, _, artifact = name.partition(":")
    if not group or not artifact:
        return []
    status, body = fetch(f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{artifact}/maven-metadata.xml")
    if status != 200:
        return []
    # Maven Central states no runtime a release needs; each is offered as the registry has it.
    return [Release(v.text or "", needs="") for v in ElementTree.fromstring(body).iter("version") if v.text]


_READERS: dict[str, Callable[[str, Fetch], list[Release]]] = {
    "npm": _npm, "pypi": _pypi, "crates": _crates, "go": _go, "maven": _maven, "rubygems": _rubygems,
    "packagist": _packagist, "nuget": _nuget,
}

#: What this process keeps that the shared store may not (a stub's answers, a run whose lookups are "off"); the
#: registry's own answers for public names live in the shared store (`lookup_service`, plan HK.12).
_CACHE: dict[tuple[str, str, Any], list[list[Any]]] = {}
_NEEDS: dict[tuple[str, str, str, Any], list[str]] = {}


def releases(ecosystem: str, name: str, *, fetch: Fetch | None = None) -> list[Release]:
    """Every release of `name` its registry lists, newest first; [] when it cannot be read. Never raises. Kept an
    hour for every run and machine (`lookup_service.releases_kept`)."""
    from app.tools import lookup_service

    reader = _READERS.get(ecosystem)
    if reader is None or not re.match(r"^[@A-Za-z0-9][@A-Za-z0-9._/:~+-]{0,213}$", name or "") or ".." in name:
        return []

    def read() -> list[list[Any]] | None:
        try:
            found = _newest_first([r for r in reader(name, fetch or _fetch_default()) if r.version])
        except Exception as exc:  # noqa: BLE001 - an unreadable registry is no answer, not a crash
            logger.info("Could not read the releases of %s %s: %s", ecosystem, name, exc)
            return None
        return [[r.version, r.released, r.needs, r.withdrawn] for r in found]

    listed = lookup_service.releases_kept(ecosystem, name, read, memo=_CACHE, memo_key=(ecosystem, name, fetch),
                                          shared=fetch is None)
    return [Release(*entry) for entry in listed or []]


def needs_of(ecosystem: str, name: str, version: str, *, fetch: Fetch | None = None) -> Release:
    """The release `version` of `name` with what it needs and whether it was withdrawn, read from its registry; its
    `needs` None when nothing could be read. Never raises."""
    version = str(version or "") if ecosystem == "go" else str(version or "").lstrip("v")
    try:
        if ecosystem in ("go", "nuget"):
            from app.tools import lookup_service

            def read() -> list[str]:
                if ecosystem == "go":
                    return list(_go_needs(name, version, fetch or _fetch_default()))
                return [_nuget_needs(name, version, fetch or _fetch_default()), ""]

            # What a published release states never changes: kept for every run and machine (plan HK.12).
            known = lookup_service.release_kept(ecosystem, name, version, read, memo=_NEEDS,
                                                memo_key=(ecosystem, name, version, fetch), shared=fetch is None)
            return Release(version, needs=known[0], withdrawn=known[1])
        for release in releases(ecosystem, name, fetch=fetch):
            if release.version.lstrip("v") == version:
                return release
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read what %s %s %s needs: %s", ecosystem, name, version, exc)
    return Release(version)


def toolchain(ecosystem: str, root: str | Path | None = None) -> str:
    """The toolchain this project's commands use for `ecosystem`: the runtime pinned for the workspace
    (`app.tools.runtimes`), else this environment's (`package_registry.runtime_here`)."""
    pinned = _PINNED_AS.get(ecosystem)
    if pinned and root:
        try:
            from app.tools import runtimes

            entry = runtimes.recorded(root).get(pinned)
            if entry and entry.get("version"):
                return f"{pinned} {entry['version']}"
        except Exception:  # noqa: BLE001 - the environment's own
            pass
    from app.tools import package_registry

    return package_registry.runtime_here(ecosystem)


def newest_that_fits(ecosystem: str, name: str, here: str, *, fetch: Fetch | None = None) -> dict[str, Any]:
    """{"version", "newest", "needs", "released", "withdrawn"} for the newest stable, not withdrawn release whose
    stated need `here` meets, and the registry's newest; {} when the registry cannot be read."""
    listed = releases(ecosystem, name, fetch=fetch)
    stable = [r for r in listed if is_stable(r.version)] or listed
    if not stable:
        return {}
    newest = stable[0]
    read_one_by_one = 0
    chosen: Release | None = None
    for release in stable:
        if release.withdrawn:
            continue
        if release.needs is None:
            if read_one_by_one >= MOST_RELEASES_READ_ONE_BY_ONE:
                break
            read_one_by_one += 1
            read = needs_of(ecosystem, name, release.version, fetch=fetch)
            release = Release(release.version, release.released, read.needs, read.withdrawn)
            if release.withdrawn:
                continue
        if fits(ecosystem, release.needs, here):
            chosen = release
            break
    if chosen is None:
        return {"version": "", "newest": newest.version, "needs": newest.needs or ""}
    released, withdrawn = chosen.released, chosen.withdrawn
    if ecosystem == "nuget" and not released:
        try:
            released, unlisted = _nuget_published(name, chosen.version, fetch or _fetch_default())
            withdrawn = withdrawn or unlisted
        except Exception:  # noqa: BLE001 - its date unknown
            pass
    return {"version": chosen.version, "newest": newest.version, "needs": chosen.needs or "",
            "released": released, "withdrawn": withdrawn}


#: Why the version offered is not the newest, as `package_registry` words it for crates and NuGet.
_NEWER_NEEDS_MORE = ("The newest release, {newest}, needs {needs}; this environment has {here}, so {version} is the "
                     "newest it builds - pin that.")
#: The key under which each registry's answer states the runtime it needs, and the field read from it.
_STATED_AS = {"npm": "node", "pypi": "python", "packagist": "php"}


def fitted(ecosystem: str, name: str, found: dict[str, Any], fetch: Fetch | None = None) -> dict[str, Any]:
    """A registry's answer for `name`, its release moved to the newest one this environment's toolchain runs when the
    current one needs a newer runtime, with a note saying so. As it was for crates and NuGet (their readers do this
    already), Maven (no field to read), an answer with an error, or when nothing could be read. Never raises."""
    try:
        if ecosystem not in ("npm", "pypi", "packagist", "rubygems", "go") or not found.get("version") or (
                "status" in found or "error" in found):
            return found
        here = toolchain(ecosystem)
        if not numbers(here):
            return found
        version = str(found["version"])
        if ecosystem in _STATED_AS:
            stated = found.get("needs_runtime") or {}
            needs = str(stated.get(_STATED_AS[ecosystem]) or "") if isinstance(stated, dict) else ""
            if not needs or needs in ("any", "not stated") or fits(ecosystem, needs, here):
                return found
        else:
            current = needs_of(ecosystem, name, version, fetch=fetch)
            needs = current.needs or ""
            if needs:
                found = {**found, "needs_runtime": {RUNTIME_OF[ecosystem]: needs}}
            if current.withdrawn:
                found = {**found, "withdrawn": current.withdrawn}
            if not needs or fits(ecosystem, needs, here):
                return found
        chosen = newest_that_fits(ecosystem, name, here, fetch=fetch)
        if not chosen.get("version") or chosen["version"] == version:
            return found
        return {**found, "version": chosen["version"], "newest_release": version,
                "needs_runtime": {RUNTIME_OF[ecosystem]: chosen.get("needs") or "not stated"},
                "note": _NEWER_NEEDS_MORE.format(newest=version, needs=f"{RUNTIME_OF[ecosystem]} {needs}", here=here,
                                                 version=chosen["version"])}
    except Exception:  # noqa: BLE001 - the registry's answer as it was
        logger.debug("Could not fit %s %s to this toolchain", ecosystem, name, exc_info=True)
        return found


__all__ = ["RUNTIME_OF", "Release", "fits", "fitted", "is_stable", "needs_of", "newest_that_fits", "numbers",
           "releases", "satisfies", "toolchain"]
