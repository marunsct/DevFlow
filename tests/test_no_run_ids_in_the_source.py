"""No run id is hardcoded anywhere in the application source or its tests.

A run id names one execution of one brief on one day. In a prompt it is noise
an agent cannot look up; in a comment or docstring it is a reference nobody can
follow once the run history is gone - and a rebuilt database removes it. The
evidence a change was made on belongs in its commit message, where it stays
next to the change it justified.

The first version of this check matched `run-` or `run ` and an id on one line,
in lower case. That let 216 through: "Run f81808a4", "Run-df4dc6f5", an id
wrapped onto the next comment line after "run", and ids listed after "runs
A, B and C". This one matches those shapes, in both directories.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: "run" or "runs", then an optional hyphen, then an id - on the same line or
#: the next, where a wrapped comment line starts with `#` or `#:`.
RUN_ID = re.compile(
    r"\bruns?-?[ \t]*(?:\n[ \t]*(?:#:?)?[ \t]*)?\b(?P<id>[0-9a-f]{8})\b",
    re.IGNORECASE,
)

#: Ids a test makes up. None of them came from a run.
PLACEHOLDERS = {"deadbeef", "abc12345"}


def _made_up(run_id: str) -> bool:
    """A placeholder: an explicit one, or one built from a repeated character."""
    return run_id in PLACEHOLDERS or "0000" in run_id or len(set(run_id)) <= 2


def _named_runs(text: str) -> list[str]:
    return sorted(
        {m.group(0).strip() for m in RUN_ID.finditer(text) if not _made_up(m.group("id").lower())}
    )


@pytest.mark.parametrize(
    "path",
    sorted(
        p
        for p in [*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]
        # This file holds real-shaped ids on purpose, to prove they are caught.
        if p.resolve() != Path(__file__).resolve()
    ),
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_the_file_names_no_run(path: Path) -> None:
    found = _named_runs(path.read_text(encoding="utf-8", errors="replace"))

    assert not found, f"{path.relative_to(ROOT)} names {found}"


class TestTheCheckItself:
    """Each shape the first version let through, and the placeholders it must not flag."""

    @pytest.mark.parametrize(
        "text",
        [
            "# Measured on run 1c9854c7's `test_round_0`",
            "Run f81808a4 spent two calls",
            "# misplaced brace. Run-df4dc6f5 took five edits",
            "# three separate sprints of run\n    # b0db10b1 - so a note",
            "    Measured on run\n    1c9854c7's `test_round_0`",
            "Measured on runs 2b5def74, da6c5e19",
        ],
    )
    def test_a_real_id_is_found(self, text: str) -> None:
        assert _named_runs(text)

    @pytest.mark.parametrize(
        "text",
        [
            "run_id = 'run-a000000c-0000-0000-0000-000000000000'",
            "'run-11111111'",
            "'run-aaaaaaa1'",
            "'run-deadbeef'",
            "'run-abc12345'",
            "runs a dozen checks",
        ],
    )
    def test_a_placeholder_is_not(self, text: str) -> None:
        assert not _named_runs(text)
