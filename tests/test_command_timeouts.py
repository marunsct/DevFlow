"""A build timeout measured on npm is not a build timeout for Rust.

`TIMEOUTS` was a four-entry table - install 300, build 180, test 300, default
120 - measured on JavaScript and applied to every language the harness can
choose. A `cargo build` compiling a dependency tree from source, a Gradle
build, a `dotnet restore`, or a first `go build` on a cold module cache all
exceed 180 seconds routinely. The command is then reported as "Command timed
out", which reads as a fault in the command, and the agent shrinks the build
rather than waiting for it.

This is root-cause class C: a constant measured on one toolchain and typed
into source. The honest fix is to derive it, and the harness cannot yet -
nothing recorded how long a command took. `_record_execution` now stores
`duration_seconds`, so the derived version has evidence to come from; until
then the scale table is an explicit ratio rather than a hidden assumption.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import (
    MAX_TIMEOUT_SECONDS,
    TIMEOUTS,
    TOOLCHAIN_TIMEOUT_SCALE,
    TOOLCHAINS,
    pin_project_stack,
    timeout_for,
)


def test_an_unpinned_workspace_keeps_the_baseline(tmp_path):
    for category, expected in TIMEOUTS.items():
        assert timeout_for(category, tmp_path) == expected


def test_a_javascript_stack_is_unchanged(tmp_path):
    """The baseline was measured here, so it must not move."""
    pin_project_stack(tmp_path, "JavaScript")
    for category, expected in TIMEOUTS.items():
        assert timeout_for(category, tmp_path) == expected


@pytest.mark.parametrize("language", ["Rust", "Java", "Kotlin", "C#", "Swift", "Scala"])
def test_a_compiled_language_gets_longer_than_the_javascript_baseline(language, tmp_path):
    pin_project_stack(tmp_path, language)
    assert timeout_for("build", tmp_path) > TIMEOUTS["build"], (
        f"a {language} build gets the same 180s as an npm build"
    )


def test_the_slowest_toolchain_in_a_full_stack_decides(tmp_path):
    """A Rust backend with a TypeScript frontend builds at Rust's pace."""
    pin_project_stack(tmp_path, "Rust", "React")
    rust_only = timeout_for("build", tmp_path)
    pin_project_stack(tmp_path, "Rust")
    assert timeout_for("build", tmp_path) == rust_only


def test_nothing_waits_longer_than_the_ceiling(tmp_path):
    pin_project_stack(tmp_path, "Scala")
    for category in TIMEOUTS:
        assert timeout_for(category, tmp_path) <= MAX_TIMEOUT_SECONDS


def test_every_toolchain_has_a_scale():
    """The set rule: a language with no scale silently gets the npm baseline."""
    missing = sorted(set(TOOLCHAINS) - set(TOOLCHAIN_TIMEOUT_SCALE))
    assert not missing, (
        f"these toolchains fall back to the JavaScript build timeout: {missing}"
    )


def test_no_scale_is_for_a_toolchain_that_does_not_exist():
    extra = sorted(set(TOOLCHAIN_TIMEOUT_SCALE) - set(TOOLCHAINS))
    assert not extra, f"scales for toolchains nothing can choose: {extra}"


def test_a_scale_never_shortens_a_timeout():
    assert all(scale >= 1.0 for scale in TOOLCHAIN_TIMEOUT_SCALE.values())


def test_an_unreadable_pin_falls_back_to_the_baseline(tmp_path):
    (tmp_path / ".project-stack").write_text("not-a-language\n", encoding="utf-8")
    assert timeout_for("build", tmp_path) == TIMEOUTS["build"]


def test_the_ledger_records_how_long_a_command_took(tmp_path, monkeypatch):
    """Without this, B3's measured timeout has no evidence to derive from."""
    import app.tools.sandbox as sandbox

    # `_ledger_path` is rooted at DATA_DIR; without this the test writes a
    # stray ledger into the repository.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sandbox, "execution_enabled", lambda: False)
    sandbox.SandboxExecutor.execute(
        command=["echo", "hi"], repo_root=str(tmp_path), role_name="testing_specialist"
    )
    entries = sandbox.read_execution_ledger(str(tmp_path))

    assert entries, "the command was not recorded at all"
    assert "duration_seconds" in entries[-1]
    assert entries[-1]["duration_seconds"] is not None
