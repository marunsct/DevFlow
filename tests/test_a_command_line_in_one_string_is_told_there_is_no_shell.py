"""A whole command line sent as one string is told there is no shell - not that a fragment of it is not permitted.

The program was taken as the line's last path part: `cd /workspace/app && cat
app/routes.py | head -50` was refused as "'routes.py | head -50' is not
permitted for role ...", with the list of permitted programs. One fixer sent
eight such lines in a minute, each told a different fragment of its own line
was not permitted, and none that there is no shell.
"""
from __future__ import annotations

import re

import pytest

from app.tools.sandbox import CommandNotAllowed, validate_command

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _refusal(command):
    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(command, "backend_specialist")
    return str(refused.value)


def test_a_joined_line_starting_with_cd_is_told_there_is_no_shell_and_to_use_the_working_directory():
    said = _refusal(["cd /workspace/tasks-api && cat tasks-api/tasks_api/routes.py | head -50"])

    assert "There is no shell here" in said and "working_directory" in said and "separate calls" in said
    assert "'routes.py | head -50' is not permitted" not in said


def test_a_redirection_is_a_joined_line_too():
    said = _refusal(["ls -la .venv/bin/python 2>/dev/null && echo yes"])
    assert "There is no shell here" in said and "'null" not in said


def test_a_permitted_program_with_its_arguments_in_one_string_is_shown_the_split_command():
    said = _refusal(["wc -l", "app/style.css"])
    assert "['wc', '-l', 'app/style.css']" in said


def test_a_proper_command_is_still_validated_as_before():
    assert validate_command(["ls", "-la"], "backend_specialist")[:1] == ["ls"]


def test_the_refusal_uses_none_of_the_banned_words():
    assert not BANNED.search(_refusal(["cd app && ls | head"]))
