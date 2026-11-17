"""A suite reopened after the build that runs out of repair rounds keeps the suite as last locked; it fails no run.

Measured on one run: a locked test was skipped by the product's own `conftest.py`, the reopened suite went five
rounds proving nothing for it, and the run failed - its product passed every hidden test and never released.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from app.graph import acceptance_nodes
from app.acceptance import junit, suite
from app.acceptance.criteria import number


def _kept(state, repairing=True):
    with mock.patch.object(suite, "is_being_repaired", return_value=repairing), \
         mock.patch.object(suite, "put_back_the_suite_before_the_repair", return_value=["acceptance/test_a.py is back"]) as back, \
         mock.patch.object(suite, "lock") as lock, \
         mock.patch.object(suite, "run", return_value=SimpleNamespace(as_dict=lambda: {"passed": 22})):
        out = acceptance_nodes._kept_as_locked_before(state, "/w", "the repaired suite proves nothing: x is skipped")
    return out, back, lock


def test_a_replanned_sprint_goes_to_the_lead():
    out, _, _ = _kept({"acceptance_return_to": acceptance_nodes.SPRINT_REPLAN})
    assert out["stage"] == "technical_lead"


def test_a_first_writing_is_not_kept():
    assert _kept({"acceptance_return_to": None})[0] is None
    assert _kept({"acceptance_return_to": "release"}, repairing=False)[0] is None


LOCKED = "test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n"


@pytest.mark.parametrize("measured, why", [
    (suite.AcceptanceResult(ran=False, problem="the suite cannot load"), "cannot run"),
    (suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=junit.Report(found=True, tests=[
        junit.TestResult(name="[AC-1] adds", outcome="skipped"),
        junit.TestResult(name="[AC-2] deletes", outcome="skipped")])), "proves nothing"),
], ids=["cannot-run", "proves-nothing"])
def test_a_repair_out_of_rounds_goes_back_where_it_came_from_with_the_suite_as_locked(tmp_path, monkeypatch, measured, why):
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n- Delete a note\n"))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(LOCKED)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] adds"])
    spec.write_text("test.skip('[AC-1] adds', async () => {});\n")
    monkeypatch.setattr(suite, "run", lambda root: measured)

    update = acceptance_nodes.acceptance_review(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "acceptance_round": acceptance_nodes.MAX_ACCEPTANCE_ROUNDS + 2,
         "acceptance_return_to": "release", "revision_comments": ["keep"],
         "document": SimpleNamespace(text="# Brief\n## Features\n- Add a note\n- Delete a note\n"),
         "product_intake": SimpleNamespace(product_name="Notes", success_measures=[])},
        {"configurable": {"thread_id": "t"}},
        acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None))

    assert update["stage"] == "release" and update["acceptance_return_to"] is None
    assert suite.is_locked(tmp_path) and spec.read_text() == LOCKED
    assert "suite as last locked was kept" in update["acceptance_open_problems"][0]
    assert why in update["acceptance_open_problems"][0]
