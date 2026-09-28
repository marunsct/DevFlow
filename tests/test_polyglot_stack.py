"""A full-stack product has two languages; the pin used to hold one.

`TechnologyStack` carries `language` and `frontend_framework`, and the stack
selector's prompt requires both filled when the product has a separate
frontend. Only `language` reached the sandbox: `pin_project_stack` took one
string, `.project-stack` held one line, and `allowed_executables` did a single
`TOOLCHAINS.get(key)`.

So a Go backend with a TypeScript frontend pinned `go`, and every code-writing
role got Go's toolchain and no `tsc`. It had not bitten yet only because
`ROLE_EXECUTABLES["ui_ux_specialist"]` hard-codes the JavaScript set - the same
accident that hid four earlier allowlist gaps - and that accident disappears
the moment a frontend is not JavaScript, or a backend role has to build one.

These tests pin the general rule: every language the stack names reaches every
role that writes code, for every combination the selector can produce.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import (
    FRAMEWORK_LANGUAGES,
    ROLE_EXECUTABLES,
    TOOLCHAINS,
    allowed_executables,
    pin_project_stack,
    project_stack,
)

#: (backend language, frontend framework) -> executables that must be reachable.
#: One row per shape of product this harness is meant to build.
FULL_STACK_COMBINATIONS = [
    (("Go", "React"), {"go", "node", "npm", "tsc"}),
    (("Python", "React"), {"python3", "pip", "node", "tsc"}),
    (("Rust", "Svelte"), {"cargo", "node", "npm"}),
    (("C#", "Angular"), {"dotnet", "node", "tsc"}),
    (("Java", "Vue"), {"java", "mvn", "node"}),
    (("Kotlin", "React"), {"gradle", "node", "tsc"}),
    (("PHP", "Vue"), {"php", "composer", "node"}),
    (("Ruby", "React"), {"ruby", "bundle", "node"}),
    (("TypeScript", "Next.js"), {"node", "npm", "tsc"}),
    (("Elixir", "Phoenix"), {"elixir", "mix"}),
    (("Dart", "Flutter"), {"dart", "flutter"}),
]


@pytest.mark.parametrize(
    "stack,required", FULL_STACK_COMBINATIONS, ids=lambda v: "-".join(v) if isinstance(v, tuple) else ""
)
def test_every_language_in_the_stack_reaches_the_roles_that_write_code(
    stack, required, tmp_path
):
    pin_project_stack(tmp_path, *stack)
    reachable = allowed_executables("backend_specialist", tmp_path) | allowed_executables(
        "ui_ux_specialist", tmp_path
    )
    missing = sorted(required - reachable)
    assert not missing, (
        f"a {stack[0]} backend with a {stack[1]} frontend cannot run: "
        f"{', '.join(missing)}"
    )


def test_a_frontend_framework_alone_still_pins_its_language(tmp_path):
    """The field names a framework, not a language, and must still resolve."""
    pin_project_stack(tmp_path, "", "React")
    assert "typescript" in project_stack(tmp_path)


def test_a_single_language_run_is_unchanged(tmp_path):
    pin_project_stack(tmp_path, "Go")
    assert project_stack(tmp_path) == frozenset({"go"})
    assert "go" in allowed_executables("backend_specialist", tmp_path)


def test_a_marker_written_before_the_pin_held_a_set_still_reads(tmp_path):
    """Backward compatibility: the old format was one line, and still is one."""
    (tmp_path / ".project-stack").write_text("rust\n", encoding="utf-8")
    assert project_stack(tmp_path) == frozenset({"rust"})
    assert "cargo" in allowed_executables("backend_specialist", tmp_path)


def test_an_unpinned_workspace_grants_nothing_extra(tmp_path):
    """No pin means the static role table and nothing more.

    Asserted on `dotnet` rather than on `cargo`: `cargo` and `go` are in the
    static `backend_specialist` table already and are granted whatever the
    stack is, which is B2 and is not this fix's to change. `dotnet` is in no
    role's table, so only a pin can grant it.
    """
    assert project_stack(tmp_path) == frozenset()
    base = allowed_executables("backend_specialist", tmp_path)
    assert "dotnet" not in base
    assert "composer" not in base


def test_an_unknown_language_pins_nothing_rather_than_failing(tmp_path):
    pin_project_stack(tmp_path, "Brainfuck", "Malbolge")
    assert project_stack(tmp_path) == frozenset()


def test_every_framework_language_names_a_real_toolchain():
    """The set rule: a framework cannot map to a toolchain that does not exist."""
    unknown = sorted(
        {language for language in FRAMEWORK_LANGUAGES.values() if language not in TOOLCHAINS}
    )
    assert not unknown, f"FRAMEWORK_LANGUAGES points at missing toolchains: {unknown}"


def test_the_pin_is_given_every_field_of_the_stack():
    """The workflow must pass the frontend framework, not only the language.

    The bug was not in the pin; it was in the one call site handing it a
    single field. A test on the pin alone would have passed throughout.
    """
    import pathlib

    node = pathlib.Path("src/app/graph/workflow.py").read_text(encoding="utf-8")
    call = node[node.index("from app.tools.sandbox import pin_project_stack") :][:1200]
    assert "frontend_framework" in call, (
        "the stack pin is called without the frontend framework, so a full-stack "
        "product gets only its backend toolchain"
    )


@pytest.mark.parametrize("role", sorted(ROLE_EXECUTABLES))
def test_no_role_loses_an_executable_when_a_second_language_is_pinned(role, tmp_path):
    """Adding a language may only widen the allowlist, never narrow it."""
    pin_project_stack(tmp_path, "Go")
    one = allowed_executables(role, tmp_path)
    pin_project_stack(tmp_path, "Go", "React")
    two = allowed_executables(role, tmp_path)
    assert one <= two


# ---------------------------------------------------------------------------
# B2's core harm, pinned as a matrix. The bug was a static per-role table:
# `go` and `cargo` appeared under one role, and `dotnet`, `mvn`, `ruby`,
# `php`, `swift` and `dart` under none, so a product in any of those could be
# written and never run. Four separate fixes each added one executable to one
# role before the toolchain table existed.
#
# This asserts the rule that generates all of them rather than any one member:
# whatever language a run pins, every role holding an allowlist can run that
# language's whole toolchain.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", sorted(TOOLCHAINS))
@pytest.mark.parametrize("role", sorted(ROLE_EXECUTABLES))
def test_every_role_can_run_every_pinned_toolchain(tmp_path, language, role):
    pin_project_stack(tmp_path, language)

    missing = sorted(TOOLCHAINS[language] - allowed_executables(role, tmp_path))

    assert not missing, (
        f"{role} cannot run {', '.join(missing)} on a {language} product, so it "
        "can write code it has no way to execute"
    )


# ---------------------------------------------------------------------------
# The resolver took the leading word, which handled "JavaScript (ES6+)" and
# failed on anything with a qualifier in front of the name.
#
# Measured live on one run: the stack selector answered "Plain JavaScript
# (ES6+)", the head word was `plain`, nothing matched, and `.project-stack`
# was written empty. Every role lost the JavaScript toolchain, so `tsc`,
# `vitest` and `playwright` were on no allowlist - in a run whose own test
# suite is Playwright. `node` and `npm` survived only because two roles
# hard-code them, which is the accident the toolchain table exists to stop
# relying on.
# ---------------------------------------------------------------------------

from app.tools.sandbox import _toolchain_key


@pytest.mark.parametrize(
    "written,expected",
    [
        ("Plain JavaScript (ES6+)", "javascript"),
        ("Vanilla JavaScript", "javascript"),
        ("plain old javascript", "javascript"),
        ("HTML/CSS/JavaScript", "javascript"),
        ("JavaScript (ES6+)", "javascript"),
        ("Modern TypeScript 5", "typescript"),
        ("Python 3.12", "python"),
        ("Go 1.22", "go"),
        ("Golang", "go"),
        ("C#", "csharp"),
        (".NET 8", "csharp"),
        ("Rust (stable)", "rust"),
        ("Ruby on Rails", "ruby"),
        ("PHP 8.3", "php"),
        ("Java 21", "java"),
        ("Kotlin/JVM", "kotlin"),
        ("Swift 5.9", "swift"),
        ("Dart 3", "dart"),
        ("Scala 3", "scala"),
    ],
)
def test_a_language_is_found_however_it_is_qualified(written, expected):
    assert _toolchain_key(written) == expected


def test_javascript_is_preferred_over_the_java_inside_it():
    """Longest match first, or every JavaScript product pins Java."""
    assert _toolchain_key("JavaScript") == "javascript"
    assert _toolchain_key("Java") == "java"


@pytest.mark.parametrize("written", ["", "None", "Assembly", "COBOL", "n/a"])
def test_something_that_names_no_known_language_pins_nothing(written):
    assert _toolchain_key(written) is None


def test_the_live_failure_now_pins_its_toolchain(tmp_path):
    """One run end to end: the selector's own words reach the allowlist."""
    pin_project_stack(tmp_path, "Plain JavaScript (ES6+)", "None – vanilla JS")

    assert project_stack(tmp_path) == frozenset({"javascript"})
    for role in ("ui_ux_specialist", "testing_specialist"):
        assert "playwright" in allowed_executables(role, tmp_path)
