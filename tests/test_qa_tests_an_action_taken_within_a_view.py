"""QA tests an action taken while a view that depends on its result is on (behind `TESTS_OF_ACTIONS_WITHIN_A_VIEW`).

Measured on one run: a brief asked for two behaviours, each had its tests, no locked test took the one while the other
was on, and the product left the wrong thing showing. An older, always-on rule already asks this of views that show
records in some state; that run's suite still went without it, so this general rule alone may not be enough.

What these tests prove: the switch puts the rule in QA's request and in the suite review's. What they do not prove:
that a model then writes such a test. Only a measured run's locked suite can show that.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import switches
from app.acceptance import requests, suite
from app.agents.acceptance_reviewer import build_acceptance_review_request
from app.observability import provenance, switch_firing

NAME = "TESTS_OF_ACTIONS_WITHIN_A_VIEW"
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "acceptance_criteria.md").write_text("- AC-1: It works.\n")
    return tmp_path


def _author(project: Path) -> str:
    return " ".join(requests.build_author_request(project, suite.criteria(project))["messages"][0]["content"].split())


def _review() -> str:
    return " ".join(build_acceptance_review_request("c", "s", "r", [], "")["messages"][0]["content"].split())


def test_with_the_switch_on_qa_tests_the_action_within_the_view_and_what_shows_afterward(monkeypatch, project):
    monkeypatch.setenv(NAME, "on")
    said = _author(project)
    assert "takes that action while that view is on" in said
    assert "what shows afterward" in said


def test_with_the_switch_on_the_suite_s_review_looks_for_it(monkeypatch):
    monkeypatch.setenv(NAME, "on")
    said = _review()
    assert "while that view is on" in said and "what shows afterward" in said


def test_with_the_switch_off_both_requests_are_as_they_were(monkeypatch, project):
    monkeypatch.setenv(NAME, "off")
    assert "what shows afterward" not in _author(project) and "what shows afterward" not in _review()


def test_the_rule_names_no_stack_product_or_control():
    from app.acceptance import actions_within_a_view

    for said in (actions_within_a_view.AUTHOR_RULE, actions_within_a_view.REVIEW_RULE, actions_within_a_view.explanation):
        assert not BANNED.search(said)


def test_the_switch_is_registered_and_armed_by_the_deployment(monkeypatch):
    # Owner, 2026-11-05: a change that affects quality is always on, with no switch.
    from app import switches as registry

    assert NAME in registry.BUILT_IN and NAME not in registry.EXPERIMENTS
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert f"{NAME}: " not in compose



def test_a_run_says_whether_the_switch_acted(monkeypatch, project):
    monkeypatch.setenv(NAME, "on")
    assert switch_firing.SIGNALS[NAME] in _author(project)
