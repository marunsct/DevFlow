"""The product started as delivered keeps the packages its install restored, though it starts from a stranger's home.

Measured on one C# run: the harness started a copy of the product as a stranger would - a fresh, empty HOME, the plain
PATH, no network. `dotnet run` restores first; with the restored packages under the agent's home out of sight and a
version range (`8.0.*`) to resolve, NuGet asked its source and failed (NU1301). The product started for the suite
every time; the check raised "does not start" in every round, every fixer reported it could not reproduce it, and two
sprint attempts were spent. A stranger runs the install first, with a network; the restored cache stands for that.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.acceptance import start_output
from app.stacks import languages


@pytest.mark.parametrize("language, variable", [("csharp", "NUGET_PACKAGES"), ("rust", "CARGO_HOME"), ("go", "GOMODCACHE")])
def test_a_toolchain_that_caches_under_home_names_its_cache(language, variable):
    assert languages.language(language).package_cache[0] == variable


@pytest.mark.parametrize("language", ["python", "javascript"])
def test_a_toolchain_that_installs_into_the_project_names_none(language):
    assert isinstance(languages.language(language).package_cache, languages.Gap)


def _a_project(tmp_path, monkeypatch, language):
    monkeypatch.setattr(start_output, "command_for", lambda root: (["sh", "start.sh"], "notes-api"))
    monkeypatch.setattr(start_output, "_as_delivered", lambda root, project: ".harness/as-delivered/product")
    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(language=language), {"project": "notes-api"}))
    seen: dict = {}

    def _execute(root, argv, where, env):
        seen.update(env)
        return {"returncode": "0", "stdout": "listening"}

    monkeypatch.setattr(start_output, "_execute", _execute)
    (tmp_path / "notes-api").mkdir()
    return seen


def test_the_restored_cache_goes_with_the_stranger_s_start(tmp_path, monkeypatch):
    seen = _a_project(tmp_path, monkeypatch, "csharp")
    (tmp_path / ".agent-home" / ".nuget" / "packages").mkdir(parents=True)

    start_output.what_it_wrote(tmp_path)

    assert seen["NUGET_PACKAGES"] == str(tmp_path / ".agent-home" / ".nuget" / "packages")
    assert seen["HOME"] != str(tmp_path / ".agent-home"), "the start still runs from a stranger's home"


def test_no_cache_is_named_where_none_was_restored(tmp_path, monkeypatch):
    seen = _a_project(tmp_path, monkeypatch, "csharp")

    start_output.what_it_wrote(tmp_path)

    assert "NUGET_PACKAGES" not in seen


def test_a_toolchain_that_restores_when_it_starts_is_started_with_a_network(tmp_path, monkeypatch):
    from app.tools import sandbox

    _a_project(tmp_path, monkeypatch, "csharp")
    granted = []
    monkeypatch.setattr(start_output, "_execute",
                        lambda *a, **k: granted.append(sandbox._A_STRANGER_S_NETWORK.get()) or {"returncode": "0"})  # noqa: SLF001

    start_output.what_it_wrote(tmp_path)

    assert granted == [True]


def test_a_toolchain_that_runs_what_was_built_is_started_with_none(tmp_path, monkeypatch):
    from app.tools import sandbox

    _a_project(tmp_path, monkeypatch, "python")
    granted = []
    monkeypatch.setattr(start_output, "_execute",
                        lambda *a, **k: granted.append(sandbox._A_STRANGER_S_NETWORK.get()) or {"returncode": "0"})  # noqa: SLF001

    start_output.what_it_wrote(tmp_path)

    assert granted == [False]


def test_only_the_harness_s_own_command_gets_the_stranger_s_network(tmp_path):
    from app.tools import sandbox

    with sandbox.with_a_stranger_s_network():
        assert sandbox._a_network_for("start", tmp_path) == "none"  # noqa: SLF001 - an agent's command, not the harness's
        token = sandbox._FOR_THE_HARNESS.set(True)  # noqa: SLF001
        try:
            assert sandbox._a_network_for("start", tmp_path) == "bridge"  # noqa: SLF001
        finally:
            sandbox._FOR_THE_HARNESS.reset(token)  # noqa: SLF001
    assert sandbox._a_network_for("start", tmp_path) == "none"  # noqa: SLF001
