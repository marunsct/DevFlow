"""No specialist is told to use tooling the run's stack did not choose.

Every specialist brief opens with `describe_stack`, so the role prompt and the
stack are in the same conversation. Four of the six role prompts used to issue
an unconditional MUST that outranked it, and the harness paid for all four:

- run-bb1ee9bb: the backend specialist "MUST ... start the development server"
  produced a 3,696-byte `server.js` in a "Web LocalStorage" product whose spec
  said "no server-side infrastructure" four times, and the milestone reviewer
  accepted it as the product.
- run 8d28ee3f: `stack_selector` chose "Custom JS assert tests ... avoiding
  large dependencies"; the UI specialist, told it MUST install NPM
  dependencies, installed jest and spent four `npm test` calls on
  `TextEncoder is not defined`.
- the testing specialist's round brief says "Do not install a test framework or
  add a dependency" while its role prompt said to install Jest or PyTest.
"""

import re

import pytest

from app.agents.specialists import _ROLE_DESCRIPTIONS, build_test_run_request

#: Naming a specific tool is what made these outrank the stack. A prompt may
#: still name `run_terminal_command` - that is the tool it calls, not a choice
#: about the product.
_TOOLS_THE_STACK_SHOULD_PICK = ("jest", "pytest", "prisma", "typeorm", "npm run build", "npx tsc")


@pytest.mark.parametrize("role", sorted(_ROLE_DESCRIPTIONS))
def test_no_role_prompt_names_a_tool_the_stack_chooses(role):
    prompt = _ROLE_DESCRIPTIONS[role].lower()
    named = [tool for tool in _TOOLS_THE_STACK_SHOULD_PICK if tool in prompt]
    assert not named, f"{role} names {named}, which is the stack's decision, not the role's"


@pytest.mark.parametrize("role", ["ui_ux", "database", "backend", "testing"])
def test_the_roles_that_build_things_defer_to_the_stack(role):
    assert "stack" in _ROLE_DESCRIPTIONS[role].lower()


def test_the_backend_is_told_what_a_serverless_stack_means():
    """The run-bb1ee9bb `server.js` came from a MUST with no such exception."""
    prompt = _ROLE_DESCRIPTIONS["backend"].lower()
    assert "no server" in prompt
    assert "second data layer" in prompt


def test_the_database_role_is_told_what_browser_storage_means():
    prompt = _ROLE_DESCRIPTIONS["database"].lower()
    assert "localstorage" in prompt
    assert "no migration to run" in prompt


def test_the_ui_role_is_told_that_no_build_step_is_a_valid_stack():
    prompt = _ROLE_DESCRIPTIONS["ui_ux"].lower()
    assert "no build tooling" in prompt


def test_the_testing_role_agrees_with_the_round_brief_it_is_given():
    """Both reach the same agent in one conversation, so they cannot disagree."""
    brief = build_test_run_request("goal", [], "/", None)["messages"][0]["content"]
    assert "Do not install a test framework" in brief

    prompt = _ROLE_DESCRIPTIONS["testing"]
    assert "Do NOT introduce a different test runner" in prompt
    assert not re.search(r"install\s+testing\s+frameworks", prompt, re.I)


def test_every_role_still_demands_working_code_not_designs():
    """The mandate that is not in conflict with the stack must survive."""
    for role in ("ui_ux", "database", "backend"):
        assert "MUST write" in _ROLE_DESCRIPTIONS[role]
    assert "Do NOT just 'design' or output snippets" in _ROLE_DESCRIPTIONS["ui_ux"]
