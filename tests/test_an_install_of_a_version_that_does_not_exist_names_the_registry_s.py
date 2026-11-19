"""An install that failed on a version the registry does not have names the version it does have, for every installer read.

Measured on one Ruby run: the Gemfile asked for `sqlite3 ~> 1.0.2`, Bundler said "Could not find gem 'sqlite3 (~> 1.0.2)'
in rubygems repository", and the note gave no registry line - npm's, PyPI's and Cargo's wording were read, Bundler's,
Composer's and NuGet's were not.
"""
from __future__ import annotations

import pytest

from app.stacks import contract
from app.tools import package_registry


@pytest.mark.parametrize("ecosystem, said, name", [
    ("rubygems", "Could not find gem 'sqlite3 (~> 1.0.2)' in rubygems repository https://rubygems.org/ or installed locally.",
     "sqlite3"),
    ("packagist", "Could not find a matching version of package slim/slim. Check the package spelling, your version "
                  "constraint", "slim/slim"),
    ("nuget", "error NU1102: Unable to find package Microsoft.Data.Sqlite with version (>= 99.0.0)",
     "Microsoft.Data.Sqlite"),
])
def test_the_registry_s_current_release_is_named(monkeypatch, ecosystem, said, name):
    asked = []

    def look_up(which, package, **_k):
        asked.append((which, package))
        return {"ecosystem": which, "package": package, "version": "2.10.2"}

    monkeypatch.setattr(package_registry, "look_up", look_up)

    note = contract._the_versions_that_exist(said)  # noqa: SLF001

    assert (ecosystem, name) in asked
    assert "2.10.2" in note
