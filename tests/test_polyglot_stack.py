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
