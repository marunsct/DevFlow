"""A prompt may only name a tool the agent actually holds.

The harness has told the model something untrue four times this session - an
allowlist offering programs the image does not have, a no-shell note
recommending `make`, a budget warning threatening a restart that never
happened, and advice naming `pytest` as its example. Each cost a stage, and
each was invisible until a run walked into it.

The tool list is the same fault with the sharpest consequence: run-db3a4a0b's
scrum master was handed "CRITICAL DIRECTORY RULES: write all document artifacts
inside `docs/`" beside "Do not write a document", went looking for the tool,
and reported "I don't have a `write_artifact` tool or any file-writing/editing
tools available" instead of returning its structured response.

`role_agent` already withholds the writing rules from a read-only agent for
exactly that reason. This checks the other direction: that nothing in a prompt
promises a tool the agent was not given.
"""

from __future__ import annotations

import re

import pytest

#: Every tool name an agent in this harness can be given.
ALL_TOOLS = frozenset({
    "ls", "read_file", "glob", "grep", "inspect_repository", "read_repository_file",
    "changed_since_sprint", "write_artifact", "edit_artifact", "delete_artifact",
    "move_artifact", "run_terminal_command", "run_validation", "read_command_output",
    "write_todos", "task",
})


def _names_in(text: str) -> set[str]:
    """Tool names the prose actually points the model at."""
    return {
        name for name in ALL_TOOLS
        if re.search(rf"`{name}`|\b{name}\(", text)
    }


def _tool_names(agent) -> set[str]:
    """The tools the compiled graph will actually run.

    Read off the `tools` node rather than the agent, because a
    `CompiledStateGraph` has no tool list of its own - which is why the first
    version of this test skipped every case and looked green.
    """
    node = (getattr(agent, "nodes", None) or {}).get("tools")
    inner = getattr(node, "bound", None) or getattr(node, "runnable", None) or node
    return set(getattr(inner, "tools_by_name", None) or {})


AGENTS = [
    ("product_manager", "create_product_manager_agent"),
    ("tools_models", "create_tools_models_agent"),
    ("stack_selector", "create_stack_selector_agent"),
    ("principal_architect", "create_principal_architect_agent"),
    ("architecture_reviewer", "create_architecture_reviewer_agent"),
    ("scrum_master", "create_scrum_master_agent"),
    ("technical_lead", "create_technical_lead_agent"),
    ("milestone_reviewer", "create_milestone_reviewer_agent"),
    ("security_reviewer", "create_security_reviewer_agent"),
]


@pytest.mark.parametrize(("module_name", "factory"), AGENTS)
def test_a_prompt_only_names_tools_the_agent_has(tmp_path, module_name, factory) -> None:
    import importlib

    module = importlib.import_module(f"app.agents.{module_name}")
    agent = getattr(module, factory)(model="gpt-4o-mini", repo_root=str(tmp_path))
    held = _tool_names(agent)
    assert held, "the tools node should always carry at least the read tools"

    # The prompt an agent actually receives is its module's own text plus ONE
    # of the two rule blocks - `role_agent` withholds the writing rules from a
    # read-only agent on purpose, and judging it against them was this test's
    # own first mistake. Which block it got is visible in what it holds.
    from app.agents.role_agent import _READ_ONLY_RULES, _WRITING_RULES

    rules = _WRITING_RULES if "write_artifact" in held else _READ_ONLY_RULES
    prompt = (getattr(module, "_SYSTEM_PROMPT", "") or "") + "\n" + rules
    promised = _names_in(prompt)
    if not promised:
        pytest.skip(f"{module_name}'s prompt names no tool")

    missing = promised - held
    assert not missing, (
        f"{module_name}'s prompt points the model at {sorted(missing)}, which it "
        "was not given. An agent that goes looking for a tool it does not have "
        "spends the stage saying so."
    )


SPECIALIST_ROLES = ["ui_ux", "database", "backend", "testing", "documentation", "security_reliability"]


@pytest.mark.parametrize("role", SPECIALIST_ROLES)
def test_a_specialist_prompt_only_names_tools_it_has(tmp_path, role: str) -> None:
    """The specialists are where this matters most.

    Their prompt is the one that points at `run_terminal_command`,
    `run_validation` and `read_command_output` - "if a command's output was
    truncated, call `read_command_output` with the reference in the truncation
    pointer" - and those arrive as `extra_tools`, from a different call site
    than the prompt.
    """
    from app.agents.role_agent import _WRITING_RULES
    from app.agents.specialists import _system_prompt, create_specialist_agent

    agent = create_specialist_agent(role, model="gpt-4o-mini", repo_root=str(tmp_path))
    held = _tool_names(agent)
    assert "write_artifact" in held, "a specialist builds the product"

    promised = _names_in(_system_prompt(role) + "\n" + _WRITING_RULES)
    assert promised, "the specialist prompt names tools; if it stops, this test is blind"

    missing = promised - held
    assert not missing, (
        f"the {role} specialist's prompt points at {sorted(missing)}, which it "
        "was not given"
    )
