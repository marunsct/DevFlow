"""The registry lookup before drafting asks Go only module paths and Maven only `group:artifact` names.

Measured over three days of runs: Go was asked 80 names and found 6 (standard-library packages such as `net/http` and
bare words), Maven 52 and found 19 (artifacts without their group); each miss cost a request and returned nothing.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import registry_versions


def _named(registry: str, *lines: str) -> list[str]:
    spec = SimpleNamespace(library_usage=[], configuration=list(lines))
    return registry_versions.named_packages(spec, registry)


def test_go_is_asked_a_module_path_and_not_a_standard_package():
    names = _named("go", "dependency modernc.org/sqlite v1.62.0", "dependency net/http v1.0", "dependency sqlite v3")

    assert names == ["modernc.org/sqlite"]


def test_maven_is_asked_group_and_artifact_and_not_a_bare_artifact():
    names = _named("maven", "dependency org.xerial:sqlite-jdbc 3.46.0", "dependency spring-boot-starter-web 3.4.0")

    assert names == ["org.xerial:sqlite-jdbc"]


def test_another_registry_keeps_bare_names():
    assert _named("pypi", "dependency flask 3.1") == ["flask"]
