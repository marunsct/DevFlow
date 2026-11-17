"""Code no review stage ever read is a completion gap (measured live).

One run's setup stage wrote the whole product; the sprint was accepted without
new work because its criteria already passed, and no code, milestone or
security review ran. The release read as reviewed work.
"""
from __future__ import annotations

import re

from app.graph import delivery
from app.observability import transcript

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _stages(monkeypatch, *names):
    monkeypatch.setattr(transcript, "read_transcript", lambda run_id, kinds=None: [{"stage": n} for n in names])


def test_a_run_with_no_review_stage_has_the_gap(monkeypatch):
    _stages(monkeypatch, "principal_architect", "stack_setup_0", "acceptance_author_0", "scrum_master")

    gaps = delivery._code_no_review_read("run-x")

    assert len(gaps) == 1 and "No review read the product's code" in gaps[0]
    assert not BANNED.search(gaps[0])


def test_a_run_whose_code_was_reviewed_has_none(monkeypatch):
    for review in ("code_review_1_0", "milestone_review", "security_review"):
        _stages(monkeypatch, "specialist_backend_0", review)
        assert delivery._code_no_review_read("run-x") == []


def test_no_transcript_claims_nothing(monkeypatch):
    _stages(monkeypatch)
    assert delivery._code_no_review_read("run-x") == []
    assert delivery._code_no_review_read(None) == []


def test_a_release_no_review_stage_read_names_it_among_its_gaps(tmp_path, monkeypatch):
    """The run's own transcript, written as the stages ran, is what the release reads."""
    from types import SimpleNamespace

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    for stage in ("principal_architect", "stack_setup_0", "scrum_master"):
        transcript.record("run-x", stage, "model_request")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    released = delivery.release(
        {"repository": SimpleNamespace(root_path=str(workspace))}, {"configurable": {"app_run_id": "run-x"}}, None,
    )

    assert released["stage"] == "complete"
    assert any("No review read the product's code" in gap for gap in released["completion_gaps"])
