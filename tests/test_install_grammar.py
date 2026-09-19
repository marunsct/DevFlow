"""A brief that forbids dependencies must forbid them in every language.

Measured on 2026-09-19 against the live guard, with a brief reading "No
external dependencies beyond basic HTML/CSS/JS":

    npm install express                 REFUSED
    pip install flask                   allowed
    cargo add serde                     allowed
    go get github.com/gin-gonic/gin     allowed
    dotnet add package Newtonsoft.Json  allowed
    bundle add rspec                    allowed
    composer require phpunit/phpunit    allowed

The check read `if not any(m in words[0] for m in ("npm","yarn","pnpm"))`, so
the constraint was enforced for JavaScript and silently unenforced for every
other stack this harness can choose. That is root-cause class H arriving
through class B: a rule defined over one member of a set.

These tests pin the rule over the whole set, so adding a language to
`TOOLCHAINS` without teaching the guard its package manager fails here rather
than in a run six weeks later.
"""

from __future__ import annotations

import pathlib

import pytest

from app.tools.sandbox import (
    _INSTALL_GRAMMAR,
    TOOLCHAINS,
    _a_package_this_command_would_add,
    _is_a_test_only_install,
    _refuse_an_install_the_brief_rules_out,
)


#: Managers that cannot add a dependency from the command line at all: in
#: these ecosystems you edit the manifest and the build tool resolves it. The
#: install guard is the wrong place for them by construction - the write path
#: is where their dependency arrives - so they are exempt here deliberately
#: rather than forgotten.
ADDS_BY_EDITING_THE_MANIFEST = frozenset({"mvn", "gradle", "kotlinc", "swift"})

#: Executables in `TOOLCHAINS` that are runtimes, compilers or test runners
#: and never install anything.
NOT_A_PACKAGE_MANAGER = frozenset({
    "node", "npx", "jest", "vitest", "mocha", "tsc", "ts-node",
    "python", "python3", "pytest", "ruff",
    "gofmt", "rustc", "rustfmt", "java", "javac",
    "kotlin", "rake", "rspec", "phpunit", "swiftc", "elixir",
    # Interpreters, not package managers. Ruby installs through `gem` and
    # `bundle`, PHP through `composer`, and all three are in the grammar. The
    # completeness test found these two on its first run, which is the test
    # working: `ruby` and `php` are in `TOOLCHAINS` beside their managers and
    # look like managers to anything that does not know the difference.
    "ruby", "php",
})


def _managers_in_toolchains() -> set[str]:
    return {
        name
        for names in TOOLCHAINS.values()
        for name in names
        if name not in NOT_A_PACKAGE_MANAGER
    }


def test_every_package_manager_the_stack_can_choose_has_install_grammar():
    """The set rule: the table covers every manager a run can actually use."""
    missing = sorted(
        name
        for name in _managers_in_toolchains()
        if name not in _INSTALL_GRAMMAR and name not in ADDS_BY_EDITING_THE_MANIFEST
    )
    assert not missing, (
        "these package managers can be chosen by the stack selector and the "
        f"install guard does not understand them: {', '.join(missing)}. A brief "
        "forbidding dependencies is silently unenforced for each."
    )


def test_no_grammar_entry_is_for_a_manager_no_stack_can_choose():
    """The other half: an entry matching nothing is dead weight that looks deliberate."""
    known = _managers_in_toolchains()
    # `bun` and `gem` are reachable through a manifest script rather than the
    # toolchain table, so they are legitimate entries with no TOOLCHAINS row.
    reachable_indirectly = {"bun", "gem"}
    orphans = sorted(set(_INSTALL_GRAMMAR) - known - reachable_indirectly)
    assert not orphans, f"grammar entries matching no toolchain: {', '.join(orphans)}"


@pytest.fixture()
def brief_forbidding_dependencies(tmp_path: pathlib.Path) -> str:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Brief\n\n## Technical Constraints\n"
        "- No external dependencies beyond basic HTML/CSS/JS\n",
        encoding="utf-8",
    )
    return str(tmp_path)


#: One production install per ecosystem. Each must be refused.
PRODUCTION_INSTALLS = [
    ["npm", "install", "express"],
    ["yarn", "add", "lodash"],
    ["pnpm", "add", "react"],
    ["bun", "add", "hono"],
    ["pip", "install", "flask"],
    ["pip3", "install", "requests"],
    ["uv", "add", "httpx"],
    ["poetry", "add", "django"],
    ["cargo", "add", "serde"],
    ["go", "get", "github.com/gin-gonic/gin"],
    ["dotnet", "add", "package", "Newtonsoft.Json"],
    ["gem", "install", "rails"],
    ["bundle", "add", "puma"],
    ["composer", "require", "monolog/monolog"],
    ["dart", "add", "http"],
]


@pytest.mark.parametrize("command", PRODUCTION_INSTALLS, ids=lambda c: c[0])
def test_a_production_install_is_refused_in_every_ecosystem(
    command, brief_forbidding_dependencies
):
    refusal = _refuse_an_install_the_brief_rules_out(command, brief_forbidding_dependencies)
    assert refusal, f"{' '.join(command)} was allowed against a brief that forbids it"
    assert command[-1] in refusal, "the refusal must name the package it refused"


#: The test-scoped twin of each ecosystem that has a dev scope. None may be
#: refused: a dependency that ships to nobody breaks no constraint on the
#: shipped product, and refusing it is what left `@playwright/test` installed
#: into `node_modules` and missing from `package.json` on run-519a9d8a.
TEST_ONLY_INSTALLS = [
    ["npm", "install", "-D", "@playwright/test"],
    ["npm", "i", "--save-dev", "jest"],
    ["yarn", "add", "--dev", "vitest"],
    ["pnpm", "add", "-D", "vitest"],
    ["uv", "add", "--dev", "pytest"],
    ["poetry", "add", "--group", "dev", "pytest"],
    ["cargo", "add", "--dev", "criterion"],
    ["bundle", "add", "rspec", "--group", "test"],
    ["composer", "require", "--dev", "phpunit/phpunit"],
    ["flutter", "add", "--dev", "mockito"],
]


@pytest.mark.parametrize("command", TEST_ONLY_INSTALLS, ids=lambda c: c[0] + "-dev")
def test_a_test_scoped_install_is_allowed_in_every_ecosystem(
    command, brief_forbidding_dependencies
):
    assert _is_a_test_only_install(command), f"{' '.join(command)} is a dev-scoped install"
    assert not _refuse_an_install_the_brief_rules_out(
        command, brief_forbidding_dependencies
    ), f"{' '.join(command)} ships to nobody and must not be refused"


#: Commands that install what a manifest already declares, or install nothing.
#: None adds a dependency, so none may be refused.
ADDS_NOTHING = [
    ["npm", "install"],
    ["pip", "install", "-r", "requirements.txt"],
    ["go", "get", "./..."],
    ["mix", "deps.get"],
    ["npx", "playwright", "install", "chromium"],
    ["node", "app.js"],
    ["pytest", "-q"],
    ["cargo", "build"],
]


@pytest.mark.parametrize("command", ADDS_NOTHING, ids=lambda c: " ".join(c[:2]))
def test_a_command_that_adds_nothing_is_never_refused(
    command, brief_forbidding_dependencies
):
    assert _a_package_this_command_would_add(command) == []
    assert not _refuse_an_install_the_brief_rules_out(
        command, brief_forbidding_dependencies
    )


def test_a_dev_flag_for_a_manager_without_a_dev_scope_is_not_an_exemption():
    """`pip` has no dev scope, so no `pip install` may claim one.

    A global flag list would exempt `pip install --dev x` on a flag pip does
    not have, which is the shape of bug this table exists to prevent.
    """
    assert not _is_a_test_only_install(["pip", "install", "--dev", "flask"])


def test_a_group_that_is_not_a_development_group_still_ships():
    assert not _is_a_test_only_install(["poetry", "add", "--group", "runtime", "redis"])
    assert _is_a_test_only_install(["poetry", "add", "--group", "dev", "pytest"])


def test_the_manager_is_matched_on_the_basename_not_by_substring():
    """`if "npm" in words[0]` also matched any path containing those letters."""
    assert _a_package_this_command_would_add(["/usr/local/bin/npm", "install", "express"])
    assert _a_package_this_command_would_add(["./tools/npm-helper", "install", "express"]) == []
