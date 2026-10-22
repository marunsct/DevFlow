"""Advice aimed at an agent must name a program the image actually has.

Measured 2026-09-16 with `shutil.which` inside the worker: `make`, `pnpm`,
`yarn`, `cargo`, `go`, `psql`, `uv`, `jasmine` and `karma` are absent, and
`pytest`, `jest`, `vitest`, `tsc`, `mocha`, `prisma` and `alembic` need a
`pip install` or an `npx` prefix first.

The same mistake was made three times in three places - the command refusal,
the stack note in every specialist brief, and the `.sh` write-time note all
recommended "a Makefile target" - so this is a test rather than a habit.
"""

from __future__ import annotations

import pytest

#: Not in the execution image and not obtainable from within a run.
ABSENT = ("make", "pnpm", "yarn", "cargo", "psql", "jasmine", "karma")


def _advice() -> dict[str, str]:
    from app.agents.specialists import NO_SHELL_NOTE
    from app.tools.repository import _unrunnable_script_note
    from app.tools.sandbox import _what_to_do_instead

    return {
        "NO_SHELL_NOTE": NO_SHELL_NOTE,
        "the .sh write note": _unrunnable_script_note("proj/build.sh"),
        "the sh refusal": _what_to_do_instead("sh"),
        "the bash refusal": _what_to_do_instead("bash"),
        "the rm refusal": _what_to_do_instead("rm"),
        "the cd refusal": _what_to_do_instead("cd"),
    }


@pytest.mark.parametrize("where", sorted(_advice()))
def test_advice_does_not_send_an_agent_to_an_absent_program(where: str) -> None:
    text = _advice()[where]
    for name in ABSENT:
        if name not in text:
            continue
        # Naming one to say it is *not* there is the point; recommending it is not.
        assert "not installed" in text or "not an option" in text, (
            f"{where} names `{name}`, which is not in the image, without saying so"
        )


def test_the_no_shell_advice_names_something_that_works() -> None:
    from app.agents.specialists import NO_SHELL_NOTE
    from app.tools.sandbox import _what_to_do_instead

    for text in (NO_SHELL_NOTE, _what_to_do_instead("sh")):
        assert "npm run" in text or "run_terminal_command" in text


def test_the_verification_example_sends_nobody_to_an_absent_program() -> None:
    """An example is strong guidance; `["pytest", "-q"]` once pointed at a
    program that is not installed. The example is now a placeholder: it names
    no program at all, so it cannot name a missing one, and it favours no
    language."""
    from app.agents.specialists import VerificationRun

    description = VerificationRun.model_fields["command"].description or ""

    for name in ("pytest", "npm", "node", "jest"):
        assert name not in description
    assert "<program>" in description
