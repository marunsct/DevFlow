"""A run on one local model gives its helpers a model to call (deep review of silent mechanisms, 2026-11-25).

The worker builds a run's graph with no model, and a run started not to use the frontier model has no judgement model,
so both were None and every helper guarding on `model is None` skipped in every local run: over 40 workspaces no
recurring cause was diagnosed (seven went to a third fix without one), no candidate fix was asked after a failed one,
and no page was scored at release, though each was switched on. Each test builds the graph as the worker does - no
model, the run on the build model only - with the deployment's default model stubbed at the factory.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.models.roles import on_the_build_model_only

CAPTURED = Path(__file__).parent / "captured" / "fix-journal-a-start-failure-failed-twice.json"
#: The cause key of the captured journal: a Go service that did not start, two fixes failed on it.
CAUSE = "start_failure:compile:notes-api/server_test.go:error|compile:notes-api/store_test.go:error|test:notes_api › testmain"


class _DefaultModel:
    """The deployment's default model, at the edge: records what it is asked and answers one JSON object."""

    def __init__(self, reply: str):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **_):
        self.asked.append(messages)
        return SimpleNamespace(content=self.reply)


def _the_default_is(model):
    return mock.patch("app.models.build_default_chat_model", lambda *a, **k: model)


def test_a_cause_that_failed_twice_is_diagnosed_in_a_local_run(tmp_path):
    import the_fix_stage
    from app.graph import cause_journal

    (tmp_path / ".harness").mkdir()
    shutil.copy(CAPTURED, tmp_path / cause_journal.FILE)
    defect = the_fix_stage.a_defect("The product does not start for the acceptance suite, so no test can reach it.",
                                    cause_key=CAUSE)
    default = _DefaultModel('{"files": ["notes-api/server.go"], "symbols": ["main"], "hypothesis": '
                            '"The route pattern in server.go panics at start; the test files were never the cause."}')

    with _the_default_is(default), on_the_build_model_only(True), \
            mock.patch.dict(os.environ, {"DIAGNOSE_A_RECURRING_CAUSE": "on"}):
        the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, defect), model=None)

    entries = json.loads((tmp_path / cause_journal.FILE).read_text())["causes"][CAUSE]["entries"]
    assert [e["hypothesis"] for e in entries if "hypothesis" in e] == [
        "The route pattern in server.go panics at start; the test files were never the cause."]


def test_a_fix_that_failed_once_gets_candidates_in_a_local_run(tmp_path):
    from app.agents.specialists import SpecialistOutput
    from workflow_nodes import a_defect, a_fix_stage

    default = _DefaultModel("unused")
    asked_of: list = []

    def candidates(defect, root, model, check, **kwargs):
        asked_of.append(model)
        return SpecialistOutput(changed_files=["app/server.js"], tests=["tests/notes.test.js"])

    once_failed = a_defect("Saving a note returns 500", fix_attempts=1)
    with _the_default_is(default), on_the_build_model_only(True), mock.patch.dict(os.environ, {"FIX_CYCLE": "on"}):
        _, fixed = a_fix_stage(tmp_path, [once_failed], patches={
            "app.graph.workflow._the_run_approves_its_own_writes": lambda run_id: True,
            "app.graph.localisation.localised": lambda *args, **kwargs: None,
            "app.graph.rewritten_fixes.what_failed": lambda *args, **kwargs: "",
            "app.graph.rewritten_fixes.files_to_fix": lambda *args, **kwargs: [],
            "app.graph.rewritten_fixes.fix_by_candidates": candidates,
        })

    assert asked_of == [default]
    assert fixed["gated"] == [], "a fixer was started although a candidate was kept"


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SCORES = json.dumps({item: {"score": 4, "note": "fine"} for item in ("layout", "contrast", "empty_states", "error_states")})


def test_a_page_is_scored_at_release_in_a_local_run(tmp_path, monkeypatch):
    from app.acceptance import screenshot_rubric
    from app.analysis import integration_checks
    from app.stacks import contract
    from workflow_nodes import run_node

    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    (tmp_path / "app" / "test-results").mkdir(parents=True)
    (tmp_path / "app" / "test-results" / "page-desktop.png").write_bytes(PNG)
    monkeypatch.setattr("app.models.vision.the_reviewer_reads_images", lambda: True)
    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    default = _DefaultModel(SCORES)

    with _the_default_is(default), on_the_build_model_only(True), \
            mock.patch.dict(os.environ, {"SCREENSHOT_RUBRIC": "on"}):
        run_node("release", {"repository": SimpleNamespace(root_path=str(tmp_path))}, str(tmp_path))

    assert json.loads((tmp_path / screenshot_rubric.RUBRIC_FILE).read_text())["mean"] == 4.0


@pytest.mark.parametrize("given, expected", [
    (SimpleNamespace(judgement_model="judge", model="build"), "judge"),
    (SimpleNamespace(judgement_model=None, model="build"), "build"),
    (SimpleNamespace(judgement_model=None, model=None), "the default"),
])
def test_the_model_a_helper_calls_is_the_judgement_model_else_the_run_s_else_the_default(given, expected):
    from app.graph.context import a_model_to_call

    with _the_default_is("the default"):
        assert a_model_to_call(given) == expected
        assert a_model_to_call(given, "the fix's own") == "the fix's own"
