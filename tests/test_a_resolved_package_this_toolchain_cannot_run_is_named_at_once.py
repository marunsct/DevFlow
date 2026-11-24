"""What an install resolved is checked against the toolchain here, and a mismatch is named at once (HK.2, LF.1293).

Measured: a Rust run's crates resolved to `icu_collections` 2.4, which needs rustc 1.88, under the image's 1.85; the
build failed round after round before anything named the cause. A C# run pinned a package release that targets
net10.0 only under .NET 8, and every restore failed NU1202 while a web lookup and two rewrites left it so. Both were
facts the lock file, the unpacked packages and the registry state exactly; the check reads them after the install and
says so in the install's own result, in the stack facts and in the first defect a test round raises.
"""
from __future__ import annotations

import json
import re

import pytest

from app.sprint import Defect
from app.stacks import stack_facts, toolchain_fit
from app.tools import package_registry as pr
from app.tools import release_fit

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _registry(pages: dict[str, object]):
    def fetch(url: str, *_a, **_k):
        for tail, body in pages.items():
            if url.endswith(tail):
                return 200, (body if isinstance(body, bytes) else json.dumps(body).encode())
        return 404, b""
    return fetch


@pytest.fixture
def registry(monkeypatch):
    """The registries stood in for (the network is the edge), the toolchains here fixed, the facts on."""
    monkeypatch.setenv("STACK_FACTS", "on")
    monkeypatch.setattr(pr, "_RUNTIMES", {"crates": "rustc 1.85.1 (4eb161250 2025-03-15)", "nuget": "8.0.428",
                                          "npm": "v24.11.1", "packagist": "PHP 8.4.1 (cli)"})
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()
    pages: dict[str, object] = {}
    monkeypatch.setattr(pr, "_fetch", lambda url, *a, **k: _registry(pages)(url))
    yield pages
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()


def _a_rust_project(root, rust_version="1.88"):
    project = root / "service"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname = "service"\n\n[dependencies]\nurl = "2"\n')
    (project / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\nname = "service"\nversion = "0.1.0"\n\n'
        '[[package]]\nname = "icu_collections"\nversion = "2.4.0"\n'
        'source = "registry+https://github.com/rust-lang/crates.io-index"\n\n'
        '[[package]]\nname = "url"\nversion = "2.5.4"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n')
    for crate, needs in (("icu_collections-2.4.0", rust_version), ("url-2.5.4", "1.63")):
        unpacked = root / ".agent-home/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f" / crate
        unpacked.mkdir(parents=True)
        (unpacked / "Cargo.toml").write_text(f'[package]\nname = "x"\nversion = "0"\nrust-version = "{needs}"\n')
    return project


CRATE = {"crate": {"max_stable_version": "2.4.0"}, "versions": [
    {"num": "2.4.0", "rust_version": "1.88", "created_at": "2026-10-01T00:00:00Z"},
    {"num": "2.2.0", "rust_version": "1.86", "created_at": "2026-06-01T00:00:00Z"},
    {"num": "2.1.1", "rust_version": "1.82", "created_at": "2026-01-01T00:00:00Z"},
]}


def test_a_crate_a_lock_resolved_that_needs_a_newer_rustc_is_named_with_the_release_that_fits(tmp_path, registry):
    project = _a_rust_project(tmp_path)
    registry["/crates/icu_collections"] = CRATE

    found = toolchain_fit.check(tmp_path, project)

    assert [(m["package"], m["version"], m["needs"], m.get("fits")) for m in found] == [
        ("icu_collections", "2.4.0", "rustc 1.88", "2.1.1")]


def _nuspec(*frameworks: str) -> bytes:
    groups = "".join(f'<group targetFramework="{f}" />' for f in frameworks)
    return f"<package><metadata><dependencies>{groups}</dependencies></metadata></package>".encode()


def test_a_nuget_release_the_project_pins_for_a_newer_net_is_named_before_any_round(tmp_path, registry):
    (tmp_path / "Api.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup>'
        '<PackageReference Include="Microsoft.Data.Sqlite" Version="11.0.0" /></ItemGroup></Project>')
    registry.update({
        "/microsoft.data.sqlite/index.json": {"versions": ["8.0.11", "9.0.4", "10.0.1", "11.0.0"]},
        "/11.0.0/microsoft.data.sqlite.nuspec": _nuspec("net10.0"),
        "/10.0.1/microsoft.data.sqlite.nuspec": _nuspec("net10.0", "net9.0"),
        "/9.0.4/microsoft.data.sqlite.nuspec": _nuspec("net8.0", "netstandard2.0"),
    })

    found = toolchain_fit.check(tmp_path, tmp_path)

    assert [(m["package"], m["version"], m.get("fits")) for m in found] == [("Microsoft.Data.Sqlite", "11.0.0", "9.0.4")]


def test_a_restore_s_assets_name_a_package_with_no_assembly_for_this_net(tmp_path, registry):
    (tmp_path / "Api.csproj").write_text('<Project><ItemGroup><PackageReference Include="Lib" Version="2.0.0" />'
                                         '</ItemGroup></Project>')
    (tmp_path / "obj").mkdir()
    (tmp_path / "obj/project.assets.json").write_text(json.dumps({"libraries": {
        "Lib/2.0.0": {"type": "package", "files": ["lib/net10.0/Lib.dll", "lib.nuspec"]},
        "Helper/1.0.0": {"type": "package", "files": ["lib/netstandard2.0/Helper.dll"]},
    }}))

    found = toolchain_fit.check(tmp_path, tmp_path)

    assert [(m["package"], m["needs"]) for m in found] == [("Lib", ".NET SDK net10.0")]


def test_npm_and_composer_locks_are_read_for_the_runtime_each_package_states(tmp_path, registry):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"framework": "^6.0.0"}}))
    (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"framework": "^6.0.0"}},
        "node_modules/framework": {"version": "6.0.0", "engines": {"node": ">=26"}},
        "node_modules/small": {"version": "1.0.0", "engines": {"node": ">=18"}},
    }}))
    php = tmp_path / "php"
    php.mkdir()
    (php / "composer.json").write_text(json.dumps({"require": {"vendor/library": "^5.0"}}))
    (php / "composer.lock").write_text(json.dumps({"packages": [
        {"name": "vendor/library", "version": "v5.0.0", "require": {"php": ">=8.5"}},
        {"name": "vendor/other", "version": "1.0.0", "require": {"php": "^8.1"}},
    ]}))

    assert [m["package"] for m in toolchain_fit.check(tmp_path, tmp_path)] == ["framework"]
    assert [m["package"] for m in toolchain_fit.check(tmp_path, php)] == ["vendor/library"]


def test_a_project_whose_resolved_packages_all_fit_is_told_nothing(tmp_path, registry):
    project = _a_rust_project(tmp_path, rust_version="1.80")

    assert toolchain_fit.check(tmp_path, project) == []
    assert toolchain_fit.described([]) == ""


def test_an_install_that_resolves_a_misfit_says_so_in_its_own_result_and_keeps_it(tmp_path, registry, monkeypatch):
    """Through the command runner, its process stood in for: the install writes the lock file it resolved."""
    from app.tools.sandbox import SandboxExecutor

    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"framework": "^6.0.0"}}))
    registry.update({
        "/framework/latest": {"name": "framework", "version": "6.0.0", "engines": {"node": ">=26"}},
        "registry.npmjs.org/framework": {"versions": {"5.5.1": {"engines": {"node": ">=22"}},
                                                      "6.0.0": {"engines": {"node": ">=26"}}}},
    })

    def install(command, repo_root, role_name, category, extra_env, working_directory):
        (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
            "": {}, "node_modules/framework": {"version": "6.0.0", "engines": {"node": ">=26"}}}}))
        return {"stdout": "added 1 package", "stderr": "", "returncode": 0}

    monkeypatch.setattr(SandboxExecutor, "_run", staticmethod(install))
    monkeypatch.setattr("app.tools.sandbox._record_execution", lambda *a, **k: None)
    monkeypatch.setattr("app.tools.sandbox._note_about_running_this_again", lambda *a, **k: "")

    outcome = SandboxExecutor.execute(["npm", "install"], str(tmp_path), category="install")

    assert toolchain_fit.FIT_CAUSE in outcome["note"]
    assert "`framework` 6.0.0" in outcome["note"] and "node >=26" in outcome["note"] and "5.5.1" in outcome["note"]
    kept = stack_facts.read(tmp_path)["mismatches"]["."]
    assert [(m["package"], m["fits"]) for m in kept] == [("framework", "5.5.1")]


def test_a_command_that_resolves_nothing_is_not_checked(tmp_path, registry, monkeypatch):
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "_run", staticmethod(lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0}))
    monkeypatch.setattr("app.tools.sandbox._record_execution", lambda *a, **k: None)
    monkeypatch.setattr("app.tools.sandbox._note_about_running_this_again", lambda *a, **k: "")

    SandboxExecutor.execute(["npm", "test"], str(tmp_path), category="test")

    assert not (tmp_path / stack_facts.SHEET).exists()


def _kept(root, *mismatches):
    sheet = root / stack_facts.SHEET
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(json.dumps({"mismatches": {"service": list(mismatches)}}))


MISFIT = {"ecosystem": "crates", "package": "icu_collections", "version": "2.4.0", "needs": "rustc 1.88",
          "toolchain": "rustc 1.85.1", "source": "Cargo.lock", "direct": False, "fits": "2.1.1"}


def _defect(description: str, actual: str = "it failed") -> Defect:
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior=actual, owner="backend")


def test_the_first_defect_after_a_misfit_carries_it_as_its_stated_cause(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_FACTS", "on")
    _kept(tmp_path, MISFIT)

    first, second = toolchain_fit.with_fit_causes(tmp_path, [_defect("The service does not build"),
                                                             _defect("A list is empty")])

    assert toolchain_fit.FIT_CAUSE in first.actual_behavior
    assert "icu_collections" in first.actual_behavior and "2.1.1" in first.actual_behavior
    assert toolchain_fit.FIT_CAUSE not in second.actual_behavior


def test_a_defect_naming_the_misfit_package_carries_it_and_never_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_FACTS", "on")
    _kept(tmp_path, MISFIT)
    defects = [_defect("A list is empty"), _defect("Build fails", "error: icu_collections 2.4.0 needs rustc 1.88")]

    once = toolchain_fit.with_fit_causes(tmp_path, defects)
    twice = toolchain_fit.with_fit_causes(tmp_path, once)

    assert toolchain_fit.FIT_CAUSE not in twice[0].actual_behavior
    assert twice[1].actual_behavior.count(toolchain_fit.FIT_CAUSE) == 1


def test_the_fit_cause_uses_none_of_the_banned_words():
    assert not BANNED.search(toolchain_fit.described([MISFIT, {**MISFIT, "fits": ""}]))
