"""The acceptance review answers without reasoning only behind `REVIEWS_WITHOUT_REASONING`, off until measured.

Measured: 68-74% of each run's output tokens were reasoning, and the acceptance review's were all reasoning. The
switch is an efficiency change, so it starts off and is kept only with no loss in quality on its on/off pairs.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.agents import reviews_without_reasoning
from app.graph import acceptance_nodes
from app.observability import provenance


def _model():
    return ChatOpenAI(model="local-model", base_url="http://localhost:9/v1", api_key="x")


def test_off_leaves_the_model_as_it_is(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "off")
    model = _model()
    assert reviews_without_reasoning.the_review_model(model) is model


def test_on_sends_the_reasoning_switch(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "on")
    from app.agents import thinking

    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    reviewed = reviews_without_reasoning.the_review_model(_model())
    assert reviewed.extra_body["chat_template_kwargs"]["enable_thinking"] is False
    assert reviewed.extra_body["reasoning_effort"] == "none"


def test_the_acceptance_review_takes_its_model_through_the_switch(tmp_path, monkeypatch):
    """The QA lead's review, run with the switch on, is built on a model that asks for no reasoning."""
    from types import SimpleNamespace

    from app.acceptance import junit, suite
    from app.acceptance.criteria import number
    from app.agents import thinking

    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "on")
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    brief = "# Brief\n## Features\n- Add a note\n- Delete a note\n"
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(brief))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n")
    monkeypatch.setattr(suite, "run", lambda root: suite.AcceptanceResult(
        ran=True, exit_code=1, command="npm run test:acceptance", report=junit.Report(found=True, tests=[
            junit.TestResult(name="[AC-1] adds", outcome="failed", message="no"),
            junit.TestResult(name="[AC-2] deletes", outcome="failed", message="no")])))
    built_on = []
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent",
                        lambda *a, model=None, **k: built_on.append(model) or object())
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", lambda state, config, *, output_key, next_stage, **k: {
        output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage})

    acceptance_nodes.acceptance_review(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "acceptance_round": 1,
         "document": SimpleNamespace(text=brief), "product_intake": SimpleNamespace(product_name="Notes", success_measures=[])},
        {"configurable": {"thread_id": "t"}},
        acceptance_nodes.Context(model=None, judgement_model=_model(), checkpointer=None, repo_root=None))

    [model] = built_on
    assert model.extra_body["chat_template_kwargs"]["enable_thinking"] is False


def test_on_with_no_judgement_model_builds_the_default_one_without_reasoning(monkeypatch):
    # Measured on the switch's first run: the judgement model was None, the switch returned it unchanged, and the
    # review reasoned as configured.
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "on")
    from app import models
    from app.agents import thinking

    monkeypatch.setattr(models, "build_default_chat_model", _model)
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    reviewed = reviews_without_reasoning.the_review_model(None)
    assert reviewed is not None
    assert reviewed.extra_body["chat_template_kwargs"]["enable_thinking"] is False


def test_off_with_no_judgement_model_leaves_it_to_the_stage(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "off")
    assert reviews_without_reasoning.the_review_model(None) is None
