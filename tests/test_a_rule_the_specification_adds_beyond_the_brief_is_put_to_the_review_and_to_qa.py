"""A rule the specification adds beyond the brief, on a subject the brief covers (behind `BRIEF_OVER_SPEC_ADDITIONS`).

Measured on one run: the architect added a rule to what a command prints, on a subject the brief had spoken to; the
tests and the code followed it, and the suite was green with a product the brief's plain reading rejects.

What these tests prove: with the switch on, the design review is given the brief's text (it had only the constraint
lines, so it could not have compared), both stages are given the rule, and with it off nothing changes. What they do
not prove: that a model obeys the rule. Only measured runs can show that.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import switches
from app.acceptance import requests, suite
from app.agents.architecture_reviewer import build_architecture_review_request
from app.observability import provenance, switch_firing

NAME = "BRIEF_OVER_SPEC_ADDITIONS"
#: A line of the brief's interface: not a constraint, so the review never saw it.
BRIEF = "# Brief\n\n## Interface\n- `report --all` prints each entry on its own line.\n\n## Technical Constraints\n- One file.\n"
LINE = "`report --all` prints each entry on its own line."
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The rule stays general: no measured case behind it is named.
TOO_NEAR_THE_CASE = re.compile(r"\b(casing|lower case|lowercase|upper case|first occurrence|benchmark|wordstats)\b", re.I)


def _review(**given) -> str:
    return build_architecture_review_request("The specification.", "/nowhere", BRIEF, **given)["messages"][0]["content"]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "acceptance_criteria.md").write_text("- AC-1: It reports.\n")
    return tmp_path


def _author(project: Path) -> str:
    return requests.build_author_request(project, suite.criteria(project), brief=BRIEF)["messages"][0]["content"]


def test_with_the_switch_on_the_review_can_compare_the_specification_with_the_brief_s_own_lines(monkeypatch):
    monkeypatch.setenv(NAME, "on")
    said = _review()
    assert LINE in said
    assert "beyond the brief" in said and "plainer reading stands" in said


def test_the_review_is_told_a_rule_on_a_subject_the_brief_leaves_alone_is_no_finding(monkeypatch):
    monkeypatch.setenv(NAME, "on")
    said = " ".join(_review().split())
    assert "subject the brief does not speak to" in said and "no finding" in said


def test_with_the_switch_off_the_review_is_as_it_was(monkeypatch):
    monkeypatch.setenv(NAME, "off")
    said = _review()
    assert LINE not in said and "plainer reading" not in said


def test_a_review_with_no_brief_is_given_no_rule_to_apply(monkeypatch):
    monkeypatch.setenv(NAME, "on")
    said = build_architecture_review_request("The specification.", "/nowhere", "")["messages"][0]["content"]
    assert "plainer reading" not in said


def test_with_the_switch_on_qa_is_told_such_a_test_is_a_choice(monkeypatch, project):
    monkeypatch.setenv(NAME, "on")
    said = " ".join(_author(project).split())
    assert "does not say, about a subject the brief does cover, is a choice" in said
    assert "plainer reading stands" in said


def test_with_the_switch_off_qa_s_request_is_as_it_was(monkeypatch, project):
    monkeypatch.setenv(NAME, "off")
    assert "plainer reading" not in _author(project)


def test_the_rule_names_nothing_it_was_measured_on(monkeypatch):
    from app.agents import brief_over_spec

    monkeypatch.setenv(NAME, "on")
    for said in (brief_over_spec.review_section("B"), brief_over_spec.QA_RULE, brief_over_spec.explanation):
        assert not BANNED.search(said)
        assert not TOO_NEAR_THE_CASE.search(said)


def test_the_switch_is_registered_and_armed_by_the_deployment(monkeypatch):
    # Owner, 2026-11-05: a change that affects quality is always on, with no switch.
    from app import switches as registry

    assert NAME in registry.BUILT_IN and NAME not in registry.EXPERIMENTS
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert f"{NAME}: " not in compose



def test_a_run_says_whether_the_switch_acted(monkeypatch):
    monkeypatch.setenv(NAME, "on")
    assert switch_firing.SIGNALS[NAME] in _review()
