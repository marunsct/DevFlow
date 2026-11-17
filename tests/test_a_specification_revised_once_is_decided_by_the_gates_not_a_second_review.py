"""A specification revised once is decided by deterministic gates, not reviewed again (LR.42 D3, `ONE_DESIGN_REVIEW`).

Every run of two families escalated at the second design review, which raised findings the first had not. With the
switch on, after one revision the workflow's own design checks and a contradiction check over the whole specification
decide: nothing open approves it, anything open goes to the design escalation as known risks.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph import one_design_review, workflow
from workflow_nodes import workflow_source

BRIEF = "# Notes\n\n- Notes with tags.\n"


def _specification(**sections):
    base = {"product_scope": "A notes service.", "deployment": ["Runs in one container."],
            "reliability_and_observability": ["Errors are logged as JSON."], "open_questions": []}
    return SimpleNamespace(**{**base, **sections})


def _state(tmp_path, specification, revisions=1):
    return {"document": SimpleNamespace(text=BRIEF), "architecture_revision_count": revisions,
            "technical_specification": specification, "repository": SimpleNamespace(root_path=str(tmp_path)),
            "decisions": [], "architecture_review": SimpleNamespace(findings=["one", "two"])}


CONTRADICTORY = _specification(
    deployment=["Graceful shutdown is supported on SIGTERM."],
    reliability_and_observability=["No graceful shutdown: the process exits at once."],
)


def test_the_gate_finds_opposite_statements_anywhere_in_the_specification_once_each():
    found = one_design_review.contradictions(CONTRADICTORY)
    assert len(found) == 1
    assert "graceful shutdown" in found[0].lower()
    assert "`deployment`" in found[0] and "`reliability_and_observability`" in found[0]
    assert one_design_review.contradictions(_specification()) == []
    # Questions state nothing, so a question is no contradiction.
    asked = _specification(deployment=["Graceful shutdown is supported."],
                           open_questions=["No graceful shutdown needed?"])
    assert one_design_review.contradictions(asked) == []


def test_on_after_one_revision_a_clean_specification_is_approved_without_a_review(monkeypatch, tmp_path):
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "on")
    monkeypatch.setattr(workflow, "_record_document", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_review_enabled", lambda state, point: False)
    state = _state(tmp_path, _specification())
    decided = workflow._decided_after_one_revision(state, "A notes service with tags.")
    assert decided["stage"] == "scaffold" and decided["architecture_review"].status == "approved"
    assert one_design_review.SAID in decided["decisions"][-1]["rationale"]


def test_on_after_one_revision_open_points_go_to_the_design_escalation(monkeypatch, tmp_path):
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "on")
    decided = workflow._decided_after_one_revision(_state(tmp_path, CONTRADICTORY), "A notes service.")
    assert decided["stage"] == "escalation"
    assert decided["escalation"]["kind"] == "design"
    assert any("graceful shutdown" in point.lower() for point in decided["escalation"]["findings"])
    assert one_design_review.SAID in decided["escalation"]["error"]


def test_off_or_before_any_revision_the_review_runs_as_before(monkeypatch, tmp_path):
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "on")
    assert workflow._decided_after_one_revision(_state(tmp_path, CONTRADICTORY, revisions=0), "x") is None
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "off")
    assert workflow._decided_after_one_revision(_state(tmp_path, CONTRADICTORY), "x") is None


def test_the_node_asks_the_gates_before_the_reviewer():
    source = workflow_source()
    gate = source.index("once = _decided_after_one_revision(state, spec_text)")
    reviewer = source.index("agent = create_architecture_reviewer_agent(", gate - 2000)
    assert gate < reviewer


def test_the_words_it_writes_name_no_product_word(monkeypatch, tmp_path):
    monkeypatch.setenv("ONE_DESIGN_REVIEW", "on")
    decided = workflow._decided_after_one_revision(_state(tmp_path, CONTRADICTORY), "A notes service.")
    text = " ".join([one_design_review.SAID, decided["escalation"]["error"], *decided["escalation"]["findings"]])
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), word
