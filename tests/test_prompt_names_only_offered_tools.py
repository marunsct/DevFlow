"""Every tool a role's prompt names is a tool that role is offered.

A small model follows the prompt. When the prompt says "write the intake in
one write_artifact call" to a role whose `can_write=False` took that tool
away, the call the model makes next is the one it was told to make - to a
tool that is not there - and the stage pays for the refusal. Removing a tool
and leaving its instructions behind is the same contradiction as forbidding
it in prose.

So every role agent is built with its real prompt and tools, and each tool
name its final system prompt mentions must be one the compiled agent offers.
"""

from __future__ import annotations

import re
import typing

import pytest

#: Tools some role is offered or that the harness has offered at some point:
#: the names a prompt could reasonably mention.
_KNOWN_ELSEWHERE = {
    "write_artifact",
    "edit_artifact",
    "replace_lines",
    "write_file",
    "edit_file",
    "run_terminal_command",
    "run_validation",
    "write_todos",
}


def _tool_names(agent) -> set[str]:
    names: set[str] = set()
    for node in getattr(agent, "nodes", {}).values():
        for attribute in ("tools_by_name", "_tools_by_name"):
            registry = getattr(getattr(node, "bound", node), attribute, None)
            if isinstance(registry, dict):
                names |= set(registry)
    return names


def _builders():
    from app.agents import (
        acceptance_reviewer,
        advice_review,
        architecture_reviewer,
        code_reviewer,
        milestone_reviewer,
        principal_architect,
        product_manager,
        scrum_master,
        security_reviewer,
        specialist_advice,
        specialists,
        stack_selector,
        suite_dispute,
        technical_lead,
        tools_models,
    )
    from app.agents.technical_lead import SpecialistRole

    roles = typing.get_args(SpecialistRole)
    builders = [
        acceptance_reviewer.create_acceptance_reviewer_agent,
        architecture_reviewer.create_architecture_reviewer_agent,
        code_reviewer.create_code_reviewer_agent,
        milestone_reviewer.create_milestone_reviewer_agent,
        principal_architect.create_principal_architect_agent,
        product_manager.create_product_manager_agent,
        scrum_master.create_scrum_master_agent,
        security_reviewer.create_security_reviewer_agent,
        stack_selector.create_stack_selector_agent,
        suite_dispute.create_suite_dispute_agent,
        technical_lead.create_technical_lead_agent,
        tools_models.create_tools_models_agent,
    ]
    for role in roles:
        builders.append(lambda role=role, **kw: specialists.create_specialist_agent(role, **kw))
        builders.append(lambda role=role, **kw: advice_review.create_advice_reviewer_agent(role, **kw))
        builders.append(lambda role=role, **kw: specialist_advice.create_specialist_advice_agent(role, **kw))
    return builders


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """{role name: (final system prompt, offered tool names)} for every role."""
    from deepagents import create_deep_agent

    import app.agents.role_agent as role_agent
    from app.models import CompatibleChatOpenAI

    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    root = tmp_path_factory.mktemp("repo")
    captured: dict[str, tuple[str, set[str]]] = {}

    def spy(**kwargs):
        agent = create_deep_agent(**kwargs)
        captured[kwargs["name"]] = (kwargs["system_prompt"], _tool_names(agent))
        return agent

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(role_agent, "create_deep_agent", spy)
        for build in _builders():
            build(model=model, repo_root=root)
    return captured


def _named_in(prompt: str, names: set[str]) -> set[str]:
    return {name for name in names if re.search(rf"(?<![\w./-]){re.escape(name)}(?![\w-])", prompt)}


def test_every_role_was_built(rendered) -> None:
    assert len(rendered) >= 15
    assert all(offered for _, offered in rendered.values())


def test_a_role_s_prompt_names_only_the_tools_it_is_offered(rendered) -> None:
    universe = set().union(*(offered for _, offered in rendered.values())) | _KNOWN_ELSEWHERE
    missing = {
        name: sorted(_named_in(prompt, universe) - offered)
        for name, (prompt, offered) in rendered.items()
    }
    assert {name: tools for name, tools in missing.items() if tools} == {}


def test_a_role_that_is_taught_to_edit_is_not_told_never_to_edit(rendered) -> None:
    """The writing rules teach `edit_artifact`; a leftover rule from when the
    role wrote one document forbade every follow-up edit."""
    told_both = [
        name
        for name, (prompt, offered) in rendered.items()
        if "edit_artifact" in offered and re.search(r"follow-up edit", prompt, re.IGNORECASE)
    ]
    assert told_both == []


def test_the_interface_specialist_may_run_the_tests_that_check_its_work(rendered) -> None:
    """Every specialist is told to prove its work by running it; the interface
    specialist was also told never to run a test - and it is the one handed a
    failing test on a page."""
    prompt, _ = rendered["specialist_ui_ux"]
    assert "Prove your work by running it" in prompt
    assert not re.search(r"do not (write, )?run(,| or)? .*tests|do not run test", prompt, re.IGNORECASE)
    assert "Do not write or change test files" in prompt


def test_the_new_rule_avoids_the_banned_words() -> None:
    from app.agents.specialists import _ROLE_DESCRIPTIONS

    text = _ROLE_DESCRIPTIONS["ui_ux"]
    rule = text[text.index("Do not write or change test files") : text.index("Return your structured")]
    banned = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    assert not {w for w in re.findall(r"[\w-]+", rule.lower())} & banned
