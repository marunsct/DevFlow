"""`loop.sh effects` says when a switch that was on never acted on a run that gave it the chance.

Measured: `SETTLE_SPEC_CONTRADICTIONS` was on, the run's design review ended with findings open, and a bug left the
switch doing nothing, without a word. Report-only.
"""
from __future__ import annotations

import re
import runpy
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from app.agents import specification_rulings
from app.decisions import render
from app.graph import escalation

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SWITCH = "SETTLE_SPEC_CONTRADICTIONS"


class _Specification(BaseModel):
    acceptance_criteria: list[str] = ["The health route answers an empty body."]
    api_and_event_contracts: list[str] = ["The health route answers JSON, as monitoring expects."]


def _report(records, decisions) -> str:
    return "\n".join(runpy.run_path(str(SCRIPT))["effects"](records, decisions))


def _on(*names) -> dict:
    return {"kind": "provenance", "switches_on": list(names)}


def _stuck(tmp_path, findings=("The specification contradicts itself about the health route.",)) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "document": SimpleNamespace(text="A health route."),
        "technical_specification": _Specification(),
        "escalation": {"kind": "design", "findings": list(findings), "error": "Still asks for changes."},
    }


def _log_of_a_run_whose_ruling_did_nothing(tmp_path, monkeypatch, findings=("A finding left open.",)) -> str:
    """The real decision, as a run with no judgement model named and no model to build reaches it."""
    monkeypatch.setenv(SWITCH, "on")

    def nothing(*_args, **_kwargs):
        raise RuntimeError("no model")

    monkeypatch.setattr("app.models.build_default_chat_model", nothing)
    update = escalation.escalation(_stuck(tmp_path, findings), {}, SimpleNamespace(judgement_model=None))
    assert not (tmp_path / specification_rulings.RULINGS_FILE).exists()
    return render(update["decisions"])


def test_on_with_findings_open_and_no_call_says_it_never_acted(tmp_path, monkeypatch):
    report = _report([_on(SWITCH)], _log_of_a_run_whose_ruling_did_nothing(tmp_path, monkeypatch))
    line = next(line for line in report.splitlines() if SWITCH in line)
    assert "NEVER ACTED" in line and "design review ended with findings open" in line
    assert not BANNED.search(line)


def test_the_call_made_is_acted_on_even_with_no_contradiction_found(tmp_path, monkeypatch):
    """Acting is making the call: a model that finds no contradiction has done the switch's work."""
    decisions = _log_of_a_run_whose_ruling_did_nothing(tmp_path, monkeypatch)
    asked = specification_rulings.the_request(["A finding."], "The specification.", "The brief.")
    report = _report([_on(SWITCH), {"kind": "model_request", "messages": [{"role": "user", "content": asked}]}], decisions)
    assert "NEVER ACTED" not in report
    assert next(line for line in report.splitlines() if SWITCH in line).strip().startswith("acted")


def test_a_review_that_passed_is_not_its_chance(tmp_path):
    report = _report([_on(SWITCH)], "# Decision log\n\n## DR-1: How is the project set up?\n- **Decision:** a pack\n")
    assert "NEVER ACTED" not in report and f"{SWITCH}: on, its condition did not arise" in report


def test_a_person_taking_the_decision_is_not_its_chance(tmp_path, monkeypatch):
    """A person's approval asks for no ruling, by design."""
    monkeypatch.setenv(SWITCH, "on")
    update = escalation.accept(_stuck(tmp_path), {}, SimpleNamespace(judgement_model=None))
    assert "NEVER ACTED" not in _report([_on(SWITCH)], render(update["decisions"]))


def test_a_decision_with_no_findings_named_is_not_its_chance(tmp_path, monkeypatch):
    decisions = _log_of_a_run_whose_ruling_did_nothing(tmp_path, monkeypatch, findings=())
    assert "NEVER ACTED" not in _report([_on(SWITCH)], decisions)


def test_off_or_on_for_part_of_the_run_is_no_claim(tmp_path, monkeypatch):
    decisions = _log_of_a_run_whose_ruling_did_nothing(tmp_path, monkeypatch)
    assert SWITCH not in _report([_on("OTHER")], decisions)
    assert SWITCH not in _report([_on("OTHER"), _on(SWITCH)], decisions)
    assert SWITCH not in _report([], decisions)


def test_more_switches_join_by_one_row(tmp_path, monkeypatch):
    from app.observability import switch_firing

    monkeypatch.setattr(switch_firing, "SIGNALS", {**switch_firing.SIGNALS, "ANOTHER": "another's own words"})
    monkeypatch.setattr(switch_firing, "CHANCES", {
        **switch_firing.CHANCES,
        "ANOTHER": switch_firing.Chance("the stage came round", re.compile("the stage came round")),
    })
    assert switch_firing.silent(["ANOTHER"], [], "the stage came round") == [("ANOTHER", "the stage came round")]
    report = _report([_on("ANOTHER")], "the stage came round")
    assert "ANOTHER" in report and "NEVER ACTED" in report


def test_every_chance_has_a_signal_and_the_gate_sees_it():
    from app.observability import switch_firing

    assert set(switch_firing.CHANCES) <= set(switch_firing.SIGNALS)
    asked = specification_rulings.the_request(["F"], "S", "B")
    assert switch_firing.SIGNALS[SWITCH] in asked
    assert switch_firing.fired([{"kind": "model_request", "messages": asked}]) == [SWITCH]
