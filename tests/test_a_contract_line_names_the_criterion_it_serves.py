"""An interface contract line names the criterion it serves, not its line number (deep review 2026-11-25, item 1).

Measured over 15 runs: in 7 the architect numbered the contract's lines 1..n - `AC-2 POST /signup -> 409` where AC-2
is "Sign in" - and the lines were handed to every builder "word for word", the release titled and charged its probes
by them, and a fixer was told the same line's criterion was a later sprint's work. The fixtures are the contracts and
criteria of real runs (`tests/captured/interface_contracts_and_criteria.json`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance.contract_ids import checked, with_the_ids_checked
from app.acceptance.interface_contract import parse

CAPTURED = json.loads((Path(__file__).parent / "captured" / "interface_contracts_and_criteria.json").read_text())


def _case(name: str) -> tuple[list[str], list[SimpleNamespace]]:
    case = CAPTURED[name]
    return case["interface_contract"], [SimpleNamespace(**c) for c in case["criteria"]]


def _line(lines: list[str], ending: str) -> str:
    return next(line for line in lines if line.endswith(ending))


def test_a_line_numbered_by_line_is_given_the_criterion_that_states_its_route():
    lines, criteria = _case("tasks_api")

    result = checked(lines, criteria).lines

    # AC-2 is "Sign in"; AC-9 is the criterion that says POST /signup answers 409.
    assert "AC-9 POST /signup -> 409" in result
    assert "AC-2 POST /signup -> 409" not in result
    assert "AC-16 GET /health -> 200" in result
    assert "AC-15 DELETE /items/{id} -> 204" in result
    # A line its own criterion speaks of is left as it was.
    assert "AC-1 POST /signup -> 201" in result


def test_a_line_no_criterion_states_loses_its_id_when_the_ids_are_line_numbers():
    lines, criteria = _case("medium_fastapi")

    result = checked(lines, criteria).lines

    # AC-6 is "Task categories and tags"; two criteria speak of registering, so neither is chosen for it.
    assert "POST /api/register -> 201" in result
    assert not any(re.match(r"AC-6 POST /api/register", line) for line in result)
    # The search field goes to "Search and filter functionality", not "Assign ... to team members".
    assert 'AC-7 page /tasks textbox "Search"' in result


def test_a_line_whose_id_is_taken_off_is_still_checked_charging_no_criterion():
    lines, criteria = _case("medium_fastapi")

    checks, unreadable = parse(checked(lines, criteria).lines)

    assert unreadable == []
    register = next(check for check in checks if check.path == "/api/register")
    username = next(check for check in checks if check.name == "Username")
    assert (register.kind, register.criterion) == ("http", "")
    assert (username.kind, username.criterion) == ("page", "")


@pytest.mark.parametrize("name", ["bookmarks"])
def test_a_contract_whose_lines_name_their_criteria_is_left_as_written(name):
    lines, criteria = _case(name)

    assert checked(lines, criteria).lines == lines


def test_a_command_line_is_given_the_criterion_that_states_the_command():
    lines, criteria = _case("wordstats_cli")

    result = checked(lines, criteria).lines

    # AC-11 is "Counts are exactly as the interface defines them"; AC-6 says "Run as python -m wordstats <file>".
    assert "AC-6 command python -m wordstats <file> -> exit 0" in result
    # AC-10 says a missing file exits with status 2: its line stands.
    assert "AC-10 command wordstats nonexistent.txt -> exit 2" in result


def test_the_specification_handed_on_carries_the_checked_lines():
    lines, criteria = _case("notes_api_java")
    from app.agents.principal_architect import TechnicalSpecificationOutput

    specification = TechnicalSpecificationOutput(interface_contract=lines)

    checked_specification = with_the_ids_checked(specification, criteria)

    # AC-6 is "Notes survive a restart"; AC-14 says GET /health answers 200.
    assert _line(checked_specification.interface_contract, "GET /health -> 200") == "AC-14 GET /health -> 200"
    assert _line(checked_specification.interface_contract, "POST /notes -> 201") == "AC-1 POST /notes -> 201"
