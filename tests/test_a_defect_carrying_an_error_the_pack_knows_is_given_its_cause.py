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


def test_a_node_test_pack_s_unit_globals_error_is_given_its_cause(tmp_path):
    """Measured on two runs: Vitest-style globals failed "describe is not defined" on `node:test`; both fixers rewrote
    the manifest the pack puts back."""
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    found = with_known_causes(tmp_path, [_defect("ReferenceError: describe is not defined")])
    assert KNOWN_CAUSE in found[0].actual_behavior and "import { describe, it } from 'node:test'" in found[0].actual_behavior
    assert not BANNED.search(found[0].actual_behavior)
    jest = tmp_path / "jest"
    contract.write(jest, pack_named("node-hono-api"), "notes", "Notes")
    assert KNOWN_CAUSE not in with_known_causes(jest, [_defect("describe is not defined")])[0].actual_behavior


def test_a_test_importing_one_directory_too_far_up_is_given_its_cause(tmp_path):
    """Measured on a held-out run: every unit test file imported the product with `../../src/...` from `test/`;
    the fixers read ERR_MODULE_NOT_FOUND as a missing file, edited the manifest and the product, and the tests shipped
    failing."""
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    text = "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/work/src/db.ts' imported from /work/notes-api/test/db.test.ts"
    found = with_known_causes(tmp_path, [_defect(text)])
    assert KNOWN_CAUSE in found[0].actual_behavior and "`../src/`, not `../../src/`" in found[0].actual_behavior
    assert not BANNED.search(found[0].actual_behavior)
