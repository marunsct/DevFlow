"""A command-line program or a library in JavaScript, TypeScript, Go or Rust starts from a pack.

Only Python had CLI and library packs; a program or library in any other
language was "a custom stack". Each new pack was scaffolded for real in the
worker image through the sandbox - install, unit smoke test, acceptance smoke
test - and passed. Acceptance meets the product as its user does: a program
run as its own process in an empty directory, a library imported by its
package name or module path, never through its internals.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.acceptance.junit import tags_in
from app.stacks import choose_pack, pack_named, supported_stacks_note
from app.stacks.packs import go_programs, node_programs, rust_programs

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
NEW = ("node-cli", "node-library", "typescript-cli", "typescript-library", "go-cli", "go-library", "rust-cli", "rust-library")


def _stack(language: str, framework: str = "None") -> SimpleNamespace:
    return SimpleNamespace(language=language, framework=framework, frontend_framework="",
                           database="", testing_framework="", product_kind="")


@pytest.mark.parametrize("language, framework, brief, chosen", [
    ("JavaScript", "None", "A command-line tool that counts words", "node-cli"),
    ("Node.js", "commander", "A CLI", "node-cli"),
    ("JavaScript", "None", "A library other programs import", "node-library"),
    ("TypeScript", "commander", "A CLI", "typescript-cli"),
    ("TypeScript", "None", "A library other programs import", "typescript-library"),
    ("Go", "cobra", "A CLI", "go-cli"),
    ("Golang", "None", "A library other programs import", "go-library"),
    ("Rust", "clap", "A command-line program", "rust-cli"),
    ("Rust", "None", "A library crate other programs import", "rust-library"),
    ("Python", "None", "A command-line tool", "python-cli"),
])
def test_each_language_s_program_and_library_gets_its_pack(language, framework, brief, chosen):
    assert choose_pack(_stack(language, framework), brief).name == chosen


@pytest.mark.parametrize("name", NEW)
def test_each_is_offered_and_renders_whole(name):
    pack = pack_named(name)
    files = pack.render("demo-app", "Demo App", "demo_app")

    assert pack.title in supported_stacks_note()
    assert not any("{{" in text for text in [*files.values(), *pack.rendered_smoke_files("demo-app", "Demo App", "demo_app").values()])
    assert set(pack.kept_files) <= set(files), "the harness keeps only files it wrote"
    assert not BANNED.search(pack.guide) and not BANNED.search(pack.acceptance_guide)


@pytest.mark.parametrize("name", ["node-cli", "typescript-cli", "go-cli", "rust-cli"])
def test_a_program_is_accepted_as_its_own_process(name):
    pack = pack_named(name)
    smoke = pack.rendered_smoke_files("demo-app", "Demo App", "demo_app")
    acceptance = next(text for path, text in smoke.items() if path.startswith(pack.acceptance_dir + "/"))

    assert re.search(r"runCli|runCLI|run_cli", acceptance)
    assert not re.search(r"from '\.\./src|crate::|demo_app::run", acceptance), "never through its internals"


@pytest.mark.parametrize("name, imported", [
    ("node-library", "from 'demo-app'"), ("typescript-library", "from 'demo-app'"),
    ("go-library", '"demo_app"'), ("rust-library", "demo_app::VERSION"),
])
def test_a_library_is_accepted_through_its_public_name(name, imported):
    pack = pack_named(name)
    smoke = pack.rendered_smoke_files("demo-app", "Demo App", "demo_app")

    assert imported in next(text for path, text in smoke.items() if path.startswith(pack.acceptance_dir + "/"))


@pytest.mark.parametrize("module, example", [
    (node_programs, "[AC-3] adds an item"), (go_programs, "Test_AC3_AddsAnItem"), (rust_programs, "ac3_adds_an_item"),
])
def test_the_naming_each_guide_teaches_carries_a_readable_criterion_id(module, example):
    assert example in module.NAMING
    assert tags_in(example) == ("AC-3",)


def test_go_acceptance_tests_never_run_with_the_unit_tests():
    pack = pack_named("go-cli")

    assert "-tags" not in pack.unit_test and "acceptance" in pack.acceptance_test
    for text in pack.rendered_smoke_files("demo-app", "Demo App", "demo_app").values():
        if "package acceptance" in text:
            assert text.startswith("//go:build acceptance")


def test_rust_smoke_tests_leave_nothing_the_crate_names():
    """A unit smoke test the library declared as a module would be missing once removed."""
    for name in ("rust-cli", "rust-library"):
        pack = pack_named(name)
        assert "src/bin/scaffold_smoke.rs" in pack.smoke_files
        assert "scaffold_smoke" not in pack.files["src/lib.rs"]


def test_typescript_runs_without_a_build_on_erasable_syntax_only():
    pack = pack_named("typescript-library")

    assert '"erasableSyntaxOnly": true' in pack.files["tsconfig.json"]
    assert "no `enum`" in pack.guide
    assert pack.kept_scripts["test"].endswith("'tests/**/*.test.ts'")


@pytest.mark.parametrize("language, framework", [
    ("TypeScript", "Hono"), ("JavaScript", "Hono"), ("TypeScript", "Elysia"), ("JavaScript", "Fastify"),
])
def test_a_framework_no_pack_knows_gets_no_pack_rather_than_another_s(language, framework):
    """Hono read as "no framework" and was given the Nest pack: only listed frameworks counted as frameworks."""
    assert choose_pack(_stack(language, framework), "A small HTTP service API") is None


@pytest.mark.parametrize("language, framework, chosen", [
    ("JavaScript", "Node.js built-in http module", "node-http-api"),
    ("Go", "net/http (standard library)", "go-http-api"),
    ("HTML, CSS, JavaScript", "Vanilla JS (ES6+)", "browser-javascript"),
    ("TypeScript", "NestJS 11", "node-nest-api"),
])
def test_a_stack_that_names_only_its_language_still_gets_its_pack(language, framework, chosen):
    text = "A small HTTP service API" if chosen != "browser-javascript" else "A web page"
    assert choose_pack(_stack(language, framework), text).name == chosen
