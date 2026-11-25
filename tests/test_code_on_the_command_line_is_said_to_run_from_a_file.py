"""The stack note says what happens to code on a command line: it is saved to a file and run (deep review 2026-11-25,
item 6).

Measured over 10 runs: 526 requests said "Code cannot be handed to a program as an argument. This is refused every
time"; of 209 inline commands sent anyway, 207 ran from a `tmp-inline-*` file, and the models that obeyed wrote, ran
and deleted 28 scratch files of their own - about 70 extra calls. The call and its answer below are a real builder's.
"""

from __future__ import annotations

import re
import shutil
from types import SimpleNamespace

import pytest

from app.agents.specialists import describe_stack
from app.tools.agent_toolkit import _code_on_the_command_line_as_a_file

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="React on Vite",
                        database="PostgreSQL", testing_framework="pytest", additional_tools=())
#: The real call, and the note its answer carried.
COMMAND = [".venv/bin/python", "-c", "import sqlalchemy; print(sqlalchemy.__version__)"]
ANSWERED = ("Ran the code you passed on the command line from `task-management-dashboard/tmp-inline-24ed957b.py`. It "
            "was saved there so what ran can be read afterwards; the harness removes the file itself before the next "
            "test round and at release - do not delete it.")


@pytest.mark.skipif(not (shutil.which("python") or shutil.which("python3")), reason="no Python on PATH to name")
def test_the_note_says_the_code_runs_from_a_saved_file(tmp_path):
    described = describe_stack(STACK, str(tmp_path))
    note = described[described.index("Code passed to a program"):]
    note = note[:note.index("\n")]

    assert "refused" not in note
    assert "`tmp-inline-*`" in note and "removes" in note
    assert "python -c" in note
    assert not BANNED.search(note)


def test_what_the_note_says_is_what_the_command_tool_does(tmp_path):
    (tmp_path / "task-management-dashboard").mkdir()

    rewritten, said = _code_on_the_command_line_as_a_file(list(COMMAND), str(tmp_path), "task-management-dashboard")

    assert rewritten[0] == ".venv/bin/python" and re.fullmatch(r"tmp-inline-[0-9a-f]{8}\.py", rewritten[1])
    assert said == ANSWERED
