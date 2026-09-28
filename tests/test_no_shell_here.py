"""A shell script in an environment that has no shell.

run-130deeef's technical specification called for a shell build script, so
`simple-to-do-list-app/build.sh` became the most-written file of the whole run
- 22 writes and edits across several stages - for a file the sandbox can never
execute. `specialist_backend_0` then sent `sh ./build.sh` five times, and
`specialist_backend_8` wrote `docs/blocker.md` five times because being blocked
was all it had left to report. The run had already completed a full sprint, a
test round, a security review and a milestone review.

Nothing in any brief said a shell was unavailable. The allowlist says so, but
only once a command has been attempted - after the spec is written, the task
delegated and the script authored.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.specialists import NO_SHELL_NOTE, describe_stack
from app.tools.repository import write_approved_artifact


@pytest.mark.parametrize("name", ["build.sh", "run.bash", "setup.zsh", "start.command"])
def test_a_shell_script_is_flagged_when_it_is_written(tmp_path, name: str) -> None:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')

    note = write_approved_artifact(tmp_path, f"proj/{name}", "echo hi\n").get("note") or ""

    assert "no shell" in note
    assert "package.json script" in note, "the alternatives that do work"


@pytest.mark.parametrize("name", ["Makefile", "app.js", "build.py", "notes.md"])
def test_what_does_run_here_is_not_flagged(tmp_path, name: str) -> None:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')

    note = write_approved_artifact(tmp_path, f"proj/{name}", "x = 1\n").get("note") or ""

    assert "no shell" not in note


def test_every_specialist_is_told_before_it_writes_one() -> None:
    """The note reaches the brief, which is earlier than the write."""
    stack = SimpleNamespace(
        language="JavaScript",
        framework="Vanilla JS",
        database="localStorage",
        testing_framework="node --test",
        additional_tools=[],
    )

    described = describe_stack(stack)

    assert NO_SHELL_NOTE in described
    assert "never a .sh file" in described


def test_the_note_only_names_programs_that_are_installed() -> None:
    """The first version offered "an npm/pnpm/yarn script, a Makefile target".

    `make`, `pnpm` and `yarn` are all three absent from the execution image -
    measured with `shutil.which` inside the worker - so three of its four
    suggestions were dead ends, in the one paragraph whose job is to say what
    to do instead.
    """
    assert "Makefile" not in NO_SHELL_NOTE
    assert "pnpm/yarn script" not in NO_SHELL_NOTE
    # A route that works, named without favouring one language: a manifest
    # script through the project's package manager, or a program run directly
    # through the tool that runs programs.
    assert "manifest" in NO_SHELL_NOTE
    assert "run_terminal_command" in NO_SHELL_NOTE


def test_a_run_with_no_recorded_stack_is_unaffected() -> None:
    assert describe_stack(None) == ""
