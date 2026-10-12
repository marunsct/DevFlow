"""An HTTP service in Go, Java, C#, Rust, Ruby or PHP starts from a pack whose tests already run.

Before, a service in any of these was "a custom stack": no scaffold, the agents
choosing the setup and the test commands, and the image holding no compiler
for any of them, so a stage could write the code and never run it. Each pack's
own two smoke tests were run in an image with the toolchains, through the
commands a run uses (`scripts/loop/verify_packs.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.acceptance import junit
from app.stacks import choose_pack, pack_named


def _service(language: str, framework: str) -> SimpleNamespace:
    return SimpleNamespace(
        language=language, framework=framework, frontend_framework="",
        database="PostgreSQL", testing_framework="", product_kind="http_api",
    )


@pytest.mark.parametrize("language, framework, chosen", [
    ("Go", "net/http (standard library)", "go-http-api"),
    ("Go 1.24", "None", "go-http-api"),
    ("Java 21", "Spring Boot", "java-spring-api"),
    ("C#", "ASP.NET Core minimal APIs", "csharp-aspnet-api"),
    (".NET 8 (C#)", "ASP.NET Core", "csharp-aspnet-api"),
    ("Rust", "axum", "rust-axum-api"),
    ("Ruby", "Sinatra", "ruby-sinatra-api"),
    ("PHP 8.4", "Slim 4", "php-slim-api"),
])
def test_a_service_in_the_language_gets_its_pack(language, framework, chosen):
    assert choose_pack(_service(language, framework), "").name == chosen


@pytest.mark.parametrize("language, framework", [
    ("Java", "Quarkus"), ("PHP", "Laravel"), ("Go", "Chi"), ("Kotlin", "Ktor"),
])
def test_a_framework_no_pack_is_built_with_gets_none(language, framework):
    """Not the language's other pack: a Quarkus service fitted the Spring Boot pack."""
    assert choose_pack(_service(language, framework), "") is None


@pytest.mark.parametrize("name", [
    "go-http-api", "java-spring-api", "csharp-aspnet-api", "rust-axum-api", "ruby-sinatra-api", "php-slim-api",
])
def test_its_acceptance_suite_is_written_one_way(name):
    """Playwright's request fixture against the running service, whatever the service is in."""
    pack = pack_named(name)
    files = pack.render("shop", "Shop", "shop")

    assert "request" in pack.acceptance_guide and "[AC-3]" in pack.acceptance_guide
    assert "/health" in files["playwright.config.js"]
    assert "playwright.config.js" in pack.kept_files
    assert pack.unit_test[0] in {"gotestsum", "mvn", "dotnet", "cargo", "bundle", "vendor/bin/phpunit"}


class TestAReportWrittenAsOneFilePerClass:
    """Maven's Surefire writes one report per test class, and cannot be asked for one."""

    def _reports(self, folder):
        folder.mkdir(parents=True)
        (folder / "TEST-app.ItemTest.xml").write_text(
            '<testsuite name="app.ItemTest"><testcase name="adds" classname="app.ItemTest"/></testsuite>'
        )
        (folder / "TEST-app.ListTest.xml").write_text(
            '<testsuite name="app.ListTest"><testcase name="lists" classname="app.ListTest">'
            '<failure message="no">no</failure></testcase></testsuite>'
        )
        (folder / "app.ItemTest.txt").write_text("not a report")
        return folder

    def test_is_read_as_one(self, tmp_path):
        report = junit.read(self._reports(tmp_path / "surefire-reports"))

        assert report.found
        assert sorted((t.name, t.outcome) for t in report.tests) == [("adds", "passed"), ("lists", "failed")]

    def test_is_cleared_as_one(self, tmp_path):
        folder = self._reports(tmp_path / "surefire-reports")

        junit.clear(folder)

        assert not junit.read(folder).found
        assert (folder / "app.ItemTest.txt").exists()

    def test_an_empty_folder_is_no_report(self, tmp_path):
        (tmp_path / "surefire-reports").mkdir()

        assert not junit.read(tmp_path / "surefire-reports").found


def test_unit_tests_beside_the_code_are_not_tests_nothing_runs(tmp_path):
    """Go's `*_test.go` sit in the package they test; `go test ./...` finds them there."""
    from app.stacks import contract
    from app.tools.repository import _tests_no_suite_runs

    project = tmp_path / "shop"
    project.mkdir()
    (project / "store_test.go").write_text("package main\n")
    contract.write(tmp_path, pack_named("go-http-api"), "shop", "Shop", "shop")

    assert _tests_no_suite_runs(tmp_path, project, [project / "store_test.go"]) == []


def test_every_command_runs_with_what_its_toolchain_needs_in_the_sandbox(tmp_path):
    """.NET died on SIGXFSZ under the sandbox's file-size limit unless W^X is off."""
    from app.tools.sandbox import _child_environment

    environment = _child_environment(str(tmp_path), None)

    assert environment["DOTNET_EnableWriteXorExecute"] == "0"


@pytest.mark.parametrize("language, framework, frontend, chosen", [
    ("TypeScript", "Next.js", "", "fullstack-next"),
    ("TypeScript", "Next.js 15", "React", "fullstack-next"),
    ("TypeScript", "Svelte", "Svelte 5", "browser-svelte"),
    ("Python", "Flask", "", "python-flask-api"),
    ("Go", "Gin", "", "go-gin-api"),
])
def test_the_major_frameworks_beside_them_get_theirs(language, framework, frontend, chosen):
    stack = SimpleNamespace(
        language=language, framework=framework, frontend_framework=frontend,
        database="", testing_framework="", product_kind="",
    )
    assert choose_pack(stack, "").name == chosen


@pytest.mark.parametrize("framework", ["Nuxt", "SvelteKit", "Remix"])
def test_a_full_stack_framework_no_pack_is_built_with_gets_none(framework):
    """Not the pack of the component framework under it: "Next.js" had fitted React on Express."""
    stack = SimpleNamespace(
        language="TypeScript", framework=framework, frontend_framework="",
        database="", testing_framework="", product_kind="",
    )
    assert choose_pack(stack, "") is None
