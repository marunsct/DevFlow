"""A ruling on the specification never has a criterion give way, and never pairs two unrelated statements (deep review
2026-11-25, item 2).

Measured over 13 runs carrying rulings: in 5 a ruling had an acceptance criterion give way to an unrelated
specification sentence - "'Returns the string ... Compact JSON string' stands, over 'AC-7: Character count includes
newlines ...'" - and a fixer told to "build and test to the statement that stands" broke the line count against AC-7;
the fix was reverted. The fixtures are the rulings and criteria of real runs
(`tests/captured/specification_rulings_and_criteria.json`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.acceptance import suite
from app.acceptance.criteria import from_records
from app.agents import specification_rulings

CAPTURED = json.loads((Path(__file__).parent / "captured" / "specification_rulings_and_criteria.json").read_text())
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_SPEC_CONTRADICTIONS", "on")

    def made(name: str) -> Path:
        case = CAPTURED[name]
        suite.save_criteria(tmp_path, from_records(case["criteria"]))
        path = tmp_path / specification_rulings.RULINGS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"rulings": case["rulings"]}), encoding="utf-8")
        return tmp_path

    return made


def test_a_ruling_over_a_criterion_is_not_shown_to_a_builder(workspace):
    section = specification_rulings.the_rulings_section(workspace("wordstats_cli"))

    assert "DR-8" in section
    for decision in ("DR-9", "DR-10", "DR-11"):
        assert decision not in section
    assert "Character count includes newlines" not in section


def test_a_ruling_on_two_different_routes_is_not_shown(workspace):
    section = specification_rulings.the_rulings_section(workspace("notes_api_javascript"))

    # "GET /health ..." over "Path parameters for /notes/{id} ...": the ruling's own reason says there is no
    # contradiction.
    assert "DR-10" not in section and "DR-11" not in section
    # Rulings about one thing stand, none of them against a criterion.
    for decision in ("DR-8", "DR-9", "DR-12"):
        assert decision in section


def test_a_ruling_whose_giving_side_cites_criteria_is_set_aside(workspace):
    section = specification_rulings.the_rulings_section(workspace("notes_api_php"))

    assert "DR-11" not in section
    assert "DR-8" in section


def test_the_reasons_say_what_the_ruling_is_instead():
    case = CAPTURED["wordstats_cli"]
    ruling = next(r for r in case["rulings"] if r["decision"] == "DR-9")

    why = specification_rulings.why_it_cannot_apply(ruling["stands"], ruling["gives_way"],
                                                    [c["text"] for c in case["criteria"]])

    assert "acceptance criterion" in why and "dispute" in why
    assert not BANNED.search(why)
