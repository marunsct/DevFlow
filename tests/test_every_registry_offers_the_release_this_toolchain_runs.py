"""Every registry's lookup offers the newest release this environment's toolchain runs, not only the newest (HK.1).

Measured: Rust runs never built on crates needing rustc 1.86-1.88 under the image's 1.85, and a C# run restored a
package for a newer .NET every round (NU1202). The crates and NuGet lookups were taught to offer the release that fits
(LF.1248); npm read `/latest` alone and PyPI the newest version alone, so a package whose current release needs a newer
Node or Python than the one here was offered at that release. Each registry states what a release needs in its own
field: npm `engines.node`, PyPI `requires_python`, RubyGems `ruby_version`, Packagist `require.php`, Go the module's
`go` directive.
"""
from __future__ import annotations

import json

import pytest

from app.tools import package_registry as pr
from app.tools import release_fit


@pytest.fixture(autouse=True)
def _environment(monkeypatch):
    monkeypatch.setattr(pr, "_RUNTIMES", {
        "npm": "v24.11.1", "pypi": "Python 3.12.3", "rubygems": "ruby 3.3.8 (2025-04-09 revision b200bad6cd)",
        "packagist": "PHP 8.4.1 (cli) (built: Nov 21 2024)", "go": "go version go1.26.9 linux/amd64",
    })
    pr._CACHE.clear()  # noqa: SLF001
    release_fit._CACHE.clear()  # noqa: SLF001
    release_fit._NEEDS.clear()  # noqa: SLF001
    yield
    pr._CACHE.clear()  # noqa: SLF001
    release_fit._CACHE.clear()  # noqa: SLF001
    release_fit._NEEDS.clear()  # noqa: SLF001


def _fetch_from(pages: dict[str, object]):
    def fetch(url: str, *_a, **_k):
        for tail, body in pages.items():
            if url.endswith(tail):
                return 200, (body if isinstance(body, bytes) else json.dumps(body).encode())
        return 404, b""
    return fetch


NPM = {
    "/latest": {"name": "framework", "version": "6.0.0", "engines": {"node": ">=26"}},
    "registry.npmjs.org/framework": {
        "versions": {
            "5.4.0": {"engines": {"node": "^20.19.0 || >=22.12.0"}},
            "5.5.0": {"engines": {"node": ">=22"}, "deprecated": "a security fault; use 5.5.1"},
            "5.5.1": {"engines": {"node": ">=22"}},
            "6.0.0": {"engines": {"node": ">=26"}},
        },
        "time": {"5.5.1": "2026-08-02T10:00:00.000Z", "6.0.0": "2026-11-01T10:00:00.000Z"},
    },
}
PYPI = {
    "/pypi/library/json": {
        "info": {"version": "3.0.0", "requires_python": ">=3.13", "summary": "x"},
        "releases": {
            "3.0.0": [{"requires_python": ">=3.13", "upload_time_iso_8601": "2026-10-01T00:00:00Z"}],
            "2.9.0": [{"requires_python": ">=3.10,<3.13", "upload_time_iso_8601": "2026-05-01T00:00:00Z", "yanked": True}],
            "2.8.0": [{"requires_python": ">=3.9", "upload_time_iso_8601": "2026-03-01T00:00:00Z"}],
            "3.0.0rc1": [{"requires_python": ">=3.12"}],
        },
    },
}
RUBYGEMS = {
    "/api/v1/gems/library.json": {"name": "library", "version": "4.0.0", "info": "x"},
    "/api/v1/versions/library.json": [
        {"number": "4.0.0", "ruby_version": ">= 3.4", "created_at": "2026-10-01T00:00:00Z", "platform": "ruby"},
        {"number": "3.9.2", "ruby_version": ">= 3.1, < 4", "created_at": "2026-06-01T00:00:00Z", "platform": "ruby"},
    ],
}
PACKAGIST = {
    "/p2/vendor/library.json": {"minified": "composer/2.0", "packages": {"vendor/library": [
        {"version": "v5.0.0", "time": "2026-10-01T00:00:00+00:00", "require": {"php": ">=8.5"}},
        {"version": "v4.2.0", "time": "2026-04-01T00:00:00+00:00", "require": {"php": "^8.2"}},
        {"version": "v4.1.0", "time": "2026-01-01T00:00:00+00:00"},
    ]}},
}
GO = {
    "/example.com/library/@latest": {"Version": "v1.9.0", "Time": "2026-10-01T00:00:00Z"},
    "/example.com/library/@v/list": b"v1.7.0\nv1.8.0\nv1.9.0\n",
    "/example.com/library/@v/v1.9.0.mod": b"module example.com/library\n\ngo 1.27.0\n",
    "/example.com/library/@v/v1.8.0.mod": b"module example.com/library\n\ngo 1.25\n",
}


@pytest.mark.parametrize("ecosystem, name, pages, fits, newest", [
    ("npm", "framework", NPM, "5.5.1", "6.0.0"),
    ("pypi", "library", PYPI, "2.8.0", "3.0.0"),
    ("rubygems", "library", RUBYGEMS, "3.9.2", "4.0.0"),
    ("packagist", "vendor/library", PACKAGIST, "4.2.0", "v5.0.0"),
    ("go", "example.com/library", GO, "v1.8.0", "v1.9.0"),
])
def test_a_package_whose_current_release_needs_a_newer_runtime_is_offered_the_newest_that_runs_here(
        ecosystem, name, pages, fits, newest):
    found = pr.look_up(ecosystem, name, fetch=_fetch_from(pages))

    assert found["version"] == fits
    assert found["newest_release"] == newest
    assert fits in found["note"] and newest in found["note"]


def test_a_current_release_this_toolchain_runs_is_offered_as_it_was():
    fetch = _fetch_from({"/latest": {"name": "small", "version": "2.0.0", "engines": {"node": ">=18"}}})

    found = pr.look_up("npm", "small", fetch=fetch)

    assert found["version"] == "2.0.0" and "newest_release" not in found


def test_a_requirement_that_cannot_be_read_holds_no_release_back():
    fetch = _fetch_from({"/latest": {"name": "odd", "version": "2.0.0", "engines": {"node": "the current one"}}})

    assert pr.look_up("npm", "odd", fetch=fetch)["version"] == "2.0.0"


@pytest.mark.parametrize("requirement, here, allowed", [
    (">=18", (24, 11, 1), True),
    (">=26", (24, 11, 1), False),
    ("^20.19.0 || >=22.12.0", (24, 11, 1), True),
    ("^20.19.0 || ^22.12.0", (24, 11, 1), False),
    (">=3.9,<3.13", (3, 12, 3), True),
    (">=3.10,<3.12", (3, 12, 3), False),
    ("!=3.12.*", (3, 12, 3), False),
    (">= 3.1, < 4", (3, 3, 8), True),
    ("~> 3.4", (3, 3, 8), False),
    ("~> 3.1", (3, 3, 8), True),
    ("^8.1 || ^9.0", (8, 4, 1), True),
    (">=8.1 <8.4", (8, 4, 1), False),
    ("~8.4.0|~8.5.0", (8, 4, 1), True),
    (">=24.12", (24,), True),
])
def test_a_stated_requirement_is_read_as_its_registry_means_it(requirement, here, allowed):
    assert release_fit.satisfies(requirement, here) is allowed
