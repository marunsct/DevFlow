"""The stack facts: one sheet of the toolchain here and each dependency's release that runs on it (HK.1, LF.1292).

Measured: stages pinned the versions they were trained on - crates for a newer rustc than the image's, a NuGet release
for a newer .NET, a gem version RubyGems never had - and each stage that asked a registry did so alone, its answer
kept for no other stage. The harness now keeps `.harness/stack-facts.json`: the toolchain versions, and for each
dependency the release chosen and why, the newest, its release date, whether it was withdrawn, what it needs, and the
version the project resolved; the stack selector, the architect, the drafting of a manifest, every fixer and the
release read it.
"""
from __future__ import annotations

import json
import re

import pytest

from app import completion_verdict
from app.stacks import stack_facts
from app.tools import package_registry as pr
from app.tools import release_fit

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

PAGES = {
    "/quickserve/latest": {"name": "quickserve", "version": "6.0.0", "engines": {"node": ">=26"}},
    "registry.npmjs.org/quickserve": {
        "versions": {"5.5.1": {"engines": {"node": ">=22"}}, "6.0.0": {"engines": {"node": ">=26"}}},
        "time": {"5.5.1": "2026-08-02T10:00:00.000Z", "6.0.0": "2026-11-01T10:00:00.000Z"},
    },
    "/old-helper/latest": {"name": "old-helper", "version": "1.2.0", "deprecated": "no longer kept"},
    "registry.npmjs.org/old-helper": {
        "versions": {"1.2.0": {"deprecated": "no longer kept; use new-helper"}},
        "time": {"1.2.0": "2019-01-01T00:00:00.000Z"},
    },
}


@pytest.fixture
def registry(monkeypatch):
    """The registry stood in for (the network is the edge), node 24 here, the facts on."""
    monkeypatch.setenv("STACK_FACTS", "on")
    monkeypatch.setattr(pr, "_RUNTIMES", {"npm": "v24.11.1"})
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()

    def fetch(url, *_a, **_k):
        for tail, body in PAGES.items():
            if url.endswith(tail):
                return 200, json.dumps(body).encode()
        return 404, b""

    monkeypatch.setattr(pr, "_fetch", fetch)
    yield
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()


def _a_project(root):
    app = root / "app"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"dependencies": {"quickserve": "^5.0.0", "old-helper": "1.2.0"}}))
    (app / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"quickserve": "^5.0.0", "old-helper": "1.2.0"}},
        "node_modules/quickserve": {"version": "5.5.1", "engines": {"node": ">=22"}},
        "node_modules/old-helper": {"version": "1.2.0"},
    }}))
    return root


def _entry(sheet, name):
    return next(d for d in sheet["dependencies"] if d["package"] == name)


def test_the_sheet_holds_the_toolchain_and_each_dependency_s_release_that_runs_here(tmp_path, registry):
    sheet = stack_facts.write(_a_project(tmp_path))

    assert sheet == stack_facts.read(tmp_path)
    assert "24.11.1" in sheet["toolchain"]["npm"]
    quickserve = _entry(sheet, "quickserve")
    assert (quickserve["version"], quickserve["newest"], quickserve["released"], quickserve["needs"],
            quickserve["resolved"], quickserve["declared_in"]) == ("5.5.1", "6.0.0", "2026-08-02", ">=22", "5.5.1", "app")
    assert "6.0.0" in quickserve["why"]


def test_a_withdrawn_release_is_marked_in_the_sheet(tmp_path, registry):
    sheet = stack_facts.write(_a_project(tmp_path))

    assert _entry(sheet, "old-helper")["withdrawn"].startswith("deprecated")


def test_before_a_manifest_the_stack_s_libraries_are_described(tmp_path, registry):
    sheet = stack_facts.write(tmp_path, libraries=["quickserve"], ecosystem="npm")

    assert [(d["package"], d["version"], d["declared_in"]) for d in sheet["dependencies"]] == [
        ("quickserve", "5.5.1", "the stack")]


def test_the_architect_s_reading_carries_the_facts_for_its_libraries(tmp_path, registry, monkeypatch):
    from types import SimpleNamespace

    from app.agents import research_brief
    from app.tools import docs

    monkeypatch.setattr(docs, "enabled", lambda: False)
    stack = SimpleNamespace(language="TypeScript", framework="quickserve", frontend_framework="", database="",
                            testing_framework="", additional_tools=[])

    notes = research_brief.research_notes(stack, "A service.", None, root=tmp_path)

    assert "quickserve 5.5.1; released 2026-08-02; needs >=22; newest 6.0.0" in notes
    assert (tmp_path / stack_facts.SHEET).is_file()


def test_every_fixer_is_told_the_toolchain_and_the_versions_resolved_in_two_lines(tmp_path, registry, monkeypatch):
    """Through the fix stage as it ships, every model call stubbed."""
    from tests import the_fix_stage

    stack_facts.write(_a_project(tmp_path))
    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path))

    request = seen.requests[0]
    assert f"{stack_facts.TOOLCHAIN_LINE} node 24.11.1." in request
    assert f"{stack_facts.VERSIONS_LINE} quickserve 5.5.1, old-helper 1.2.0 (withdrawn: deprecated" in request


def test_the_stack_selector_is_told_the_toolchains_this_environment_runs(registry, monkeypatch):
    monkeypatch.setattr(pr, "_RUNTIMES", {"npm": "v24.11.1", "pypi": "Python 3.12.3", "crates": "not installed",
                                          "go": "not installed", "maven": "not installed", "rubygems": "not installed",
                                          "packagist": "not installed", "nuget": "8.0.428"})

    section = stack_facts.toolchains_section()

    assert "node 24.11.1" in section and "python 3.12.3" in section and ".NET SDK 8.0.428" in section
    assert "rustc" not in section


def test_a_manifest_s_drafting_is_told_the_toolchain_its_packages_run_on(tmp_path, registry):
    stack_facts.write(_a_project(tmp_path))

    assert stack_facts.toolchain_line(tmp_path, "npm").startswith(f"{stack_facts.TOOLCHAIN_LINE} node 24.11.1.")


def test_the_release_names_a_withdrawn_dependency_and_a_misfit_as_notes(tmp_path, registry):
    stack_facts.write(_a_project(tmp_path), mismatches={"app": [{
        "package": "quickserve", "version": "6.0.0", "needs": "node >=26", "toolchain": "v24.11.1"}]})

    gaps = stack_facts.release_gaps(tmp_path)

    assert len(gaps) == 2 and "old-helper" in gaps[0] and "quickserve 6.0.0" in gaps[1]
    assert completion_verdict.verdict(gaps) == completion_verdict.DELIVERED


def test_off_nothing_is_written_or_said(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_FACTS", "off")

    assert stack_facts.write(_a_project(tmp_path)) == {}
    assert stack_facts.for_a_fixer(tmp_path) == stack_facts.toolchains_section() == ""
    assert not (tmp_path / stack_facts.SHEET).exists()


def test_the_words_each_stage_is_given_use_none_of_the_banned_ones(tmp_path, registry):
    stack_facts.write(_a_project(tmp_path), mismatches={"app": [{
        "package": "quickserve", "version": "6.0.0", "needs": "node >=26", "toolchain": "v24.11.1", "fits": "5.5.1"}]})

    texts = [stack_facts.toolchains_section(), stack_facts.for_a_fixer(tmp_path), stack_facts.toolchain_line(tmp_path, "npm"),
             stack_facts.library_lines(tmp_path, None, []), *stack_facts.release_gaps(tmp_path)]

    assert all(texts[:3]) and not any(BANNED.search(text) for text in texts)
