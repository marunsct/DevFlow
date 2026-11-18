"""A manifest or build file of any language is build configuration, not the application.

Deep review 2026-11-18, item E3: the file classifier read `Cargo.toml`, `pom.xml`, `*.csproj`, `Gemfile` and
`phpunit.xml` as the product's own code - each stage's file ranking, role and "product code" rules then treated a
build file as the application. The manifests now come from the language table.
"""

from __future__ import annotations

import pytest

from app.analysis.file_kinds import classify_file


@pytest.mark.parametrize("path", [
    "Cargo.toml", "pom.xml", "build.gradle.kts", "src/App/App.csproj", "Gemfile", "phpunit.xml", "composer.json",
    "go.mod", "package.json", "pyproject.toml",
])
def test_a_manifest_is_configuration(path):
    assert classify_file(path) == "config"


@pytest.mark.parametrize("path, kind", [
    ("tests/UnitTests/UnitTests.csproj", "test"),
    ("Cargo.lock", "vendored"),
    ("packages.lock.json", "vendored"),
    ("src/main.rs", "application"),
    ("src/Program.cs", "application"),
    ("app.rb", "application"),
])
def test_what_is_not_a_manifest_keeps_its_kind(path, kind):
    """A test project's file stays a test; lock files stay vendored; source stays the application."""
    assert classify_file(path) == kind
