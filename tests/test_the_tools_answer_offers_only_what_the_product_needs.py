"""The tools-and-models answer offers only the comparison sections the intake's kind of product needs (plan PA.14).

Measured over 11 small runs: the answer compared queue systems, observability and model providers for a notes
service and a word counter, and listed 47 open questions; the stack selector read all of it.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.agents.tools_models import TechnologyChoice, ToolsAndModelsOutput
from app.state import RepositoryContext
from workflow_nodes import a_served_model, run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

A_COMMAND_LINE_INTAKE = json.dumps({
    "product_name": "Word stats",
    "core_workflows": ["Run the command-line tool on a text file and read the word counts it prints"],
    "constraints": ["Runs from a terminal; reads files from disk"],
})


def _a_choice(category: str) -> TechnologyChoice:
    return TechnologyChoice(category=category, name="x", capability="c", compatibility="c", quality="q",
                            latency="l", cost="c", privacy="p", licensing="l", operational_burden="o",
                            alternative="a", replacement_criteria="r")


def test_a_command_line_product_is_offered_no_queue_provider_or_deployment_section():
    from app.agents.tools_models import sections_for

    offered = sections_for(A_COMMAND_LINE_INTAKE)

    assert {"frameworks", "storage_options", "testing_tools"} <= set(offered)
    assert not {"queue_and_job_systems", "model_providers", "observability", "deployment_options",
                "authentication"} & set(offered)


def test_a_section_the_kind_does_not_need_is_offered_when_the_intake_asks_for_it():
    from app.agents.tools_models import sections_for

    intake = json.dumps({"product_name": "Reports", "core_workflows": [
        "The REST API accepts a report request and a background job queue builds it; users sign in first"]})

    offered = sections_for(intake)

    assert {"queue_and_job_systems", "authentication", "deployment_options"} <= set(offered)
    assert "model_providers" not in offered


def test_with_no_kind_to_tell_every_section_is_offered_as_before():
    from app.agents.tools_models import sections_for

    assert len(sections_for(json.dumps({"product_name": "Something"}))) == 8


def test_the_stage_sends_the_model_only_the_offered_sections_and_keeps_none_it_was_not_offered(tmp_path):
    model, sent = a_served_model()
    from app.agents import tools_models

    def built(**kwargs):
        return tools_models.create_tools_models_agent(**{**kwargs, "model": model})

    def gated(state, config, *, agent, initial_request, output_key, **kwargs):
        try:
            agent.invoke(initial_request, {"configurable": {"thread_id": "tools"}, "recursion_limit": 4})
        except Exception:  # noqa: BLE001 - the served model answers in prose; the request it was sent is what is read
            pass
        # An answer that fills a section it was not offered anyway.
        return {output_key: ToolsAndModelsOutput(frameworks=[_a_choice("framework")],
                                                 queue_and_job_systems=[_a_choice("queue")]),
                "stage": "stack_selector"}

    state = {
        "product_intake": json.loads(A_COMMAND_LINE_INTAKE),
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "document": SimpleNamespace(text="A word counter run from a terminal."),
    }
    update = run_node("tools_models", state, str(tmp_path), {
        "app.graph.workflow.create_tools_models_agent": built,
        "app.graph.workflow._run_gated_agent": gated,
    })

    answer_tool = next(tool["function"] for tool in sent[0]["tools"]
                       if tool["function"]["name"] == "ToolsAndModelsOutput")
    properties = answer_tool["parameters"]["properties"]
    assert "frameworks" in properties and "testing_tools" in properties
    assert "queue_and_job_systems" not in properties and "model_providers" not in properties
    assert update["tools_models"].queue_and_job_systems == []
    assert [choice.name for choice in update["tools_models"].frameworks] == ["x"]


def test_the_rule_the_tools_architect_is_told_uses_none_of_the_banned_words():
    from app.agents.tools_models import _SYSTEM_PROMPT

    rule = _SYSTEM_PROMPT.split("Responsibilities:", 1)[1].split("- For every choice", 1)[0]
    assert "schema offers" in rule
    assert not BANNED.search(rule)
