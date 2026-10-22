"""`NAME=value program` is said to set nothing, in a plan and at run time (measured live).

A plan's verification and a stage's own command both put a variable in front of a
program, as a shell reads it. There is no shell: the plan check skipped the
command because its first word is not a known program, so the plan went out, and
the stage's call was refused with only a list of the programs allowed.
"""
from __future__ import annotations

import re

import pytest

from app.analysis.planned_commands import commands_the_sandbox_would_refuse
from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_plan_check_flags_a_variable_before_a_program(tmp_path):
    notes = commands_the_sandbox_would_refuse(
        "`SECRET_VALUE=abc node acceptance/run.mjs`", "testing_specialist", tmp_path
    )

    assert len(notes) == 1
    assert "sets nothing" in notes[0]


def test_the_plan_check_leaves_a_plain_command_alone(tmp_path):
    assert commands_the_sandbox_would_refuse("`node acceptance/run.mjs`", "testing_specialist", tmp_path) == []


def test_a_stage_s_refused_assignment_says_why(tmp_path):
    with pytest.raises(sandbox.CommandNotAllowed) as refused:
        sandbox.validate_command(["SECRET_VALUE=abc", "node", "x.mjs"], "testing_specialist", tmp_path)

    assert "sets nothing" in str(refused.value)


def test_the_advice_uses_none_of_the_banned_words():
    assert not BANNED.search(sandbox.ASSIGNMENT_ADVICE)


def test_env_in_front_of_a_command_is_refused_with_the_same_advice(tmp_path):
    with pytest.raises(sandbox.CommandNotAllowed) as refused:
        sandbox.validate_command(["env", "SECRET_VALUE=abc", "node", "x.mjs"], "testing_specialist", tmp_path)

    assert "sets nothing" in str(refused.value)
