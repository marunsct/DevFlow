"""An error the product prints while every test passes is a defect.

One run's last test round ran three suites, all green. One printed
"QuotaExceededError is not defined" from the product's storage adapter, which
tested `e instanceof QuotaExceededError` - a class that is not a global in a
browser or in Node. The failure path the brief asked for threw instead of
recovering. The round called the line "a non-fatal warning", listed it under
`risks`, and the milestone passed.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.specialists import build_test_run_request


def _brief(tmp_path: Path) -> str:
    request = build_test_run_request("Persist tasks", ["app.js"], str(tmp_path), None)
    return " ".join(request["messages"][0]["content"].split())


def test_the_round_is_told_to_read_what_a_passing_run_printed(tmp_path: Path) -> None:
    brief = _brief(tmp_path)

    assert "A passing exit code is not the whole result: read what the run printed" in brief


def test_such_an_error_goes_in_defects_not_risks(tmp_path: Path) -> None:
    brief = _brief(tmp_path)

    assert "a name that is not defined" in brief
    assert "is a defect in the code that printed it, not a risk" in brief
    assert "Report it in `defects`" in brief


def test_the_wording_names_no_language(tmp_path: Path) -> None:
    rule = _brief(tmp_path).split("A passing exit code", 1)[1]

    for name in ("QuotaExceededError", "localStorage", "instanceof", "console", "Node", "npm"):
        assert name not in rule
