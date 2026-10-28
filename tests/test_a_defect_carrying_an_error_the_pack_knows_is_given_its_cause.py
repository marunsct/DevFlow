"""A defect whose text carries an error the stack pack knows is given that error's cause.

Measured on one run: `c.body('', 204)` threw "Invalid response status code 204" on a Hono service on Node; two fixes
did not change that call and the sprint was planned again over a one-line fix.
"""
from __future__ import annotations

import inspect
import re

from app.agents.specialists import ReportedDefect
from app.graph import workflow
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _defect(text):
    return ReportedDefect(description=f"The unit tests fail. It says: {text}", severity="major",
                          reproduction_steps="npm test", expected_behavior="they pass", actual_behavior=text,
                          affected_files=[], owner="backend")


def test_a_hono_project_s_204_error_is_given_its_cause_once(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    first = with_known_causes(tmp_path, [_defect("TypeError: Response constructor: Invalid response status code 204")])
    assert KNOWN_CAUSE in first[0].actual_behavior and "`c.body(null, 204)`" in first[0].actual_behavior
    assert not BANNED.search(first[0].actual_behavior)
    again = with_known_causes(tmp_path, first)
    assert again[0].actual_behavior.count(KNOWN_CAUSE) == 1
    other = with_known_causes(tmp_path, [_defect("AssertionError: expected 200")])
    assert KNOWN_CAUSE not in other[0].actual_behavior


def test_both_hono_packs_know_it_and_a_project_without_a_pack_is_left(tmp_path):
    assert pack_named("node-hono-api").known_errors == pack_named("node-hono-native-api").known_errors != {}
    raw = [_defect("Invalid response status code 204")]
    assert with_known_causes(tmp_path, raw) == raw


def test_the_round_adds_the_causes():
    assert 'reported = with_known_causes(state["repository"].root_path, reported)' in inspect.getsource(workflow)
