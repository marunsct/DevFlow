"""A package lookup offers the newest release this environment's toolchain can build, not only the newest release.

Measured on two runs of one day: a Rust manifest pinned `rusqlite` 0.43, which needs rustc 1.89, under the image's
1.85 ("rustc 1.85.0 is not supported by the following packages"); a C# project pinned `Microsoft.Data.Sqlite` 11.0.0,
which targets net10.0 only, under the image's .NET 8 (NU1202). Both lookups answered the registry's newest release.
"""
from __future__ import annotations

import json

import pytest

from app.tools import package_registry as pr


@pytest.fixture(autouse=True)
def _environment(monkeypatch):
    monkeypatch.setattr(pr, "_RUNTIMES", {"crates": "rustc 1.85.1 (4eb161250 2025-03-15)", "nuget": "8.0.428"})
    pr._CACHE.clear()  # noqa: SLF001
    yield
    pr._CACHE.clear()  # noqa: SLF001


def _fetch_from(pages: dict[str, object]):
    def fetch(url: str, *_a, **_k):
        for tail, body in pages.items():
            if url.endswith(tail):
                return 200, (body if isinstance(body, bytes) else json.dumps(body).encode())
        return 404, b""
    return fetch


CRATE = {
    "crate": {"max_stable_version": "0.43.0", "newest_version": "0.43.0", "description": "SQLite"},
    "versions": [
        {"num": "0.43.0", "rust_version": "1.89", "yanked": False},
        {"num": "0.42.0", "rust_version": "1.89", "yanked": False},
        {"num": "0.37.0", "rust_version": "1.82.0", "yanked": False},
        {"num": "0.36.0", "rust_version": None, "yanked": False},
    ],
}


def test_a_crate_whose_newest_release_needs_a_newer_rustc_is_offered_the_one_this_rustc_builds():
    found = pr.look_up("crates", "rusqlite", fetch=_fetch_from({"/crates/rusqlite": CRATE}))

    assert found["version"] == "0.37.0"
    assert found["newest_release"] == "0.43.0"


def _nuspec(*frameworks: str) -> bytes:
    groups = "".join(f'<group targetFramework="{f}" />' for f in frameworks)
    return f'<package><metadata><dependencies>{groups}</dependencies></metadata></package>'.encode()


def test_a_nuget_package_whose_newest_release_targets_a_newer_framework_is_offered_one_for_this_sdk():
    fetch = _fetch_from({
        "/microsoft.data.sqlite/index.json": {"versions": ["8.0.0", "9.0.4", "10.0.1", "11.0.0"]},
        "/11.0.0/microsoft.data.sqlite.nuspec": _nuspec("net10.0"),
        "/10.0.1/microsoft.data.sqlite.nuspec": _nuspec("net10.0", "net9.0"),
        "/9.0.4/microsoft.data.sqlite.nuspec": _nuspec("net8.0", "netstandard2.0"),
    })

    found = pr.look_up("nuget", "Microsoft.Data.Sqlite", fetch=fetch)

    assert found["version"] == "9.0.4"
    assert found["newest_release"] == "11.0.0"


def test_a_newest_release_this_environment_builds_is_offered_as_it_was():
    fetch = _fetch_from({
        "/serde/index.json": {"versions": ["1.0.200"]},
        "/1.0.200/serde.nuspec": _nuspec("netstandard2.0"),
    })

    found = pr.look_up("nuget", "serde", fetch=fetch)

    assert found["version"] == "1.0.200" and "newest_release" not in found
