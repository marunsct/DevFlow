"""The C# pack names the two top-level-statement rules that broke the entry file's build.

Measured on two runs (C# 13 and 14): `Program.cs` failed to compile on "The modifier 'public' is not valid for this item"
and on "A static local function cannot contain a reference to 'connectionString'", and the fixers rewrote the file
for rounds without being told the rule.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def _behaviour(tmp_path, said: str) -> str:
    contract.write(tmp_path, pack_named("csharp-aspnet-api"), "notes-api", "Notes")
    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not build.", severity="major", reproduction_steps="dotnet build",
        expected_behavior="it builds", actual_behavior=said, affected_files=[], owner="backend")])
    return defect.actual_behavior


def test_a_public_local_function_is_given_the_modifier_rule(tmp_path):
    said = "notes-api/src/App/Program.cs line 37: The modifier 'public' is not valid for this item"

    behaviour = _behaviour(tmp_path, said)

    assert KNOWN_CAUSE in behaviour and "no access modifier" in behaviour


def test_a_static_local_function_capture_is_given_its_rule(tmp_path):
    said = "Program.cs line 82: A static local function cannot contain a reference to 'connectionString'"

    behaviour = _behaviour(tmp_path, said)

    assert KNOWN_CAUSE in behaviour and "pass the value in as a parameter" in behaviour
