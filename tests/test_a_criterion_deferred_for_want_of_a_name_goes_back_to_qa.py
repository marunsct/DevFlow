"""A criterion deferred only because no test's name carries its id goes back to QA, not out deferred (behind `NAMING_FINDING_BEFORE_DEFERRAL`).

Measured on recent runs: a criterion shipped "deferred, unproven" while what was missing was an id in a test's name.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app import switches
from app.acceptance import suite
from app.graph import acceptance_nodes, delivery, escalation
from app.observability import provenance
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(root, reasons, text="test('lists the notes', async () => {});\ntest('[AC-3] search', async () => {});\n"):
    contract.write(root, pack_named("node-hono-native-api"), "notes", "Notes")
    where = root / "notes" / "acceptance"
    where.mkdir(parents=True)
    (where / "api.spec.js").write_text(text)
    from app.acceptance.criteria import Criterion

    suite.save_criteria(root, [Criterion(id=f"AC-{n}", text=f"criterion {n}", source="brief") for n in (1, 2, 3)], reasons)
    return {"repository": SimpleNamespace(root_path=str(root))}


REASONS = {
    "AC-1": "could not be made to pass after fixes and re-planning (x)",
    "AC-2": "needs a third party's approval",  # QA's reason, judged at the review
    "AC-3": "its locked test cannot pass whatever is built",  # a test carries it
}


def test_only_the_harness_s_deferral_with_no_carrier_goes_back_and_once(tmp_path, monkeypatch):
    state = _project(tmp_path, REASONS)
    monkeypatch.setenv("NAMING_FINDING_BEFORE_DEFERRAL", "on")
    back = acceptance_nodes.naming_back_to_qa(state)
    assert back["stage"] == "acceptance_author" and back["acceptance_return_to"] == "release"
    named = [item for item in back["acceptance_feedback"] if "would ship deferred" in item]
    assert len(named) == 1 and named[0].startswith("AC-1 ") and "`AC-1`" in named[0]
    assert not BANNED.search(named[0])
    assert acceptance_nodes.naming_back_to_qa(state) is None


def test_off_nothing_goes_back(tmp_path, monkeypatch):
    state = _project(tmp_path, REASONS)
    monkeypatch.setenv("NAMING_FINDING_BEFORE_DEFERRAL", "off")
    assert acceptance_nodes.naming_back_to_qa(state) is None


def test_the_release_sends_it_back_before_measuring(tmp_path, monkeypatch):
    from app.graph import workflow

    state = _project(tmp_path, REASONS)
    monkeypatch.setenv("NAMING_FINDING_BEFORE_DEFERRAL", "on")
    monkeypatch.setattr(workflow, "_stop_if_cancelled", lambda run: None)
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    def never(root):
        raise AssertionError("the suite was measured first")
    monkeypatch.setattr(suite, "run", never)
    assert delivery.release(state, {"configurable": {}}, SimpleNamespace())["stage"] == "acceptance_author"


def test_a_repair_may_rename_a_test_but_not_drop_one(tmp_path):
    _project(tmp_path, REASONS)
    relative = "notes/acceptance/api.spec.js"
    kept = tmp_path / suite.SNAPSHOT_DIR / relative
    kept.parent.mkdir(parents=True)
    kept.write_text("test('lists the notes', async () => {});\ntest('[AC-3] search', async () => {});\n")
    suite.repairing(tmp_path, [suite.NAMING_REPAIR])
    renamed = "test('[AC-1] lists the notes', async () => {});\ntest('[AC-3] search', async () => {});\n"
    assert suite.tests_a_repair_would_drop(tmp_path, relative, renamed) == []
    assert suite.tests_a_repair_would_drop(tmp_path, relative, "test('[AC-1] lists the notes', async () => {});\n") != []


def test_the_prefixes_are_the_ones_the_harness_writes():
    assert "could not be made to pass after" in inspect.getsource(escalation) and suite.DEFERRED_BY_THE_HARNESS[0] == "could not be made to pass"
    assert suite.DEFERRED_BY_THE_HARNESS[1] in inspect.getsource(acceptance_nodes.defer_what_is_beyond_repair)


def test_the_switch_is_registered_and_off(monkeypatch):
    monkeypatch.delenv("NAMING_FINDING_BEFORE_DEFERRAL", raising=False)
    assert "NAMING_FINDING_BEFORE_DEFERRAL" in switches.EXPERIMENTS and "NAMING_FINDING_BEFORE_DEFERRAL" not in switches.EXPERIMENTS_ON
    assert "NAMING_FINDING_BEFORE_DEFERRAL" in provenance.SWITCHES
    assert provenance.switch(provenance.SWITCHES["NAMING_FINDING_BEFORE_DEFERRAL"]).enabled() is False
