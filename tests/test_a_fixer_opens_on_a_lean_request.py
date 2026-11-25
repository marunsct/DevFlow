"""A fixer opens on its own lean request (plan FX.3, LF.1417-LF.1419).

Measured on a medium run: every fixer was built as its owner's builder - the builder's system prompt, about 21,000
characters, and sixteen tools whose descriptions came to 23,564 - and, with its request and memory, opened at
26,400-34,000 tokens against a 43,020-token summary trigger, 61-79% of it before its first read. Over 54 runs, fixers
called five tools for nearly every call and never called `move_artifact`, `read_docs` or `research`. The opening
target sized the message alone, and six blocks of what the failing tests printed said one thing five times.
"""
from __future__ import annotations

import re

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Stopped(Exception):
    pass


class _Seen(BaseChatModel):
    """Records the system prompt and the tools of the first call, then stops the stage."""

    prompts: list[str] = []
    offered: list[list[str]] = []

    @property
    def _llm_type(self) -> str:
        return "seen"

    def bind_tools(self, tools, **kwargs):
        self.offered.append([getattr(t, "name", None) or t.get("name", "") for t in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(str(messages[0].content))
        raise _Stopped()


def _opened(root, monkeypatch, role: str = "backend", **kwargs) -> tuple[str, set[str]]:
    """The system prompt and tools a fixer of `role`'s defect is opened with."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.specialists import create_specialist_agent

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role, **k: "")
    model = _Seen(prompts=[], offered=[])
    agent = create_specialist_agent(role, model=model, repo_root=str(root), checkpointer=InMemorySaver(),
                                    fixing=True, **kwargs)
    with pytest.raises(_Stopped):
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    return model.prompts[0], set(model.offered[-1]) - {"task"}


def test_a_fixer_is_offered_its_few_tools_and_its_answer(tmp_path, monkeypatch):
    _, offered = _opened(tmp_path, monkeypatch)

    # `module_exports` joins only where the run offers it (`lean_fixer.WHEN_OFFERED`): on with the production defaults.
    assert offered - {"module_exports"} == {"read_file", "grep", "edit_artifact", "write_artifact", "delete_artifact",
                                            "run_terminal_command", "read_command_output", "SpecialistOutput"}


def test_a_fixer_whose_defect_failed_twice_keeps_the_web_tools_it_is_given(tmp_path, monkeypatch):
    from langchain_core.tools import tool

    @tool
    def search_the_web(query: str) -> str:
        """Search the web."""
        return ""

    _, offered = _opened(tmp_path, monkeypatch, web_tools_for_this_fix=[search_the_web])

    assert "search_the_web" in offered and "read_docs" not in offered


@pytest.mark.parametrize("role", ["backend", "ui_ux", "testing", "database"])
def test_a_fixer_s_prompt_is_short_and_names_only_the_tools_it_is_offered(tmp_path, monkeypatch, role):
    prompt, offered = _opened(tmp_path, monkeypatch, role)

    named = set(re.findall(r"`([a-z_]+)`", prompt)) & {
        "ls", "glob", "delete_artifact", "move_artifact", "look_at_page", "read_docs", "research", "look_up_package",
        "module_exports", "run_validation", "replace_lines", "write_todos", *offered}
    assert named <= offered
    # About a third of the builder's 15,000 characters before the stack's guidance.
    assert len(prompt) <= 7_000
    assert not BANNED.search(prompt)


def test_a_fixer_s_prompt_keeps_the_rules_that_bind_any_change(tmp_path, monkeypatch):
    prompt, _ = _opened(tmp_path, monkeypatch, "backend")

    assert "Never remove or disable application logic" in prompt
    assert "never add a route or command" in prompt
    assert "locked acceptance suite" in prompt and "never write there" in prompt
    # The owner's own product rule: a request the service cannot use is refused with a 4xx.
    assert "refused with a 4xx" in prompt
    assert "`blockers`" in prompt


# --- what its failing tests printed ----------------------------------------------------------------------------

_SAME = ("    Error: expect(received).toBe(expected)\n\n    Expected: 201\n    Received: 500\n\n"
         "        at /workspace/shop/acceptance/auth.spec.js:{line}:29\n\n"
         "    Error Context: ../test-results/evidence/auth-{slug}/error-context.md")
_OTHER = ("    Error: expect(received).toBe(expected)\n\n    Expected: 401\n    Received: 429\n\n"
          "        at /workspace/shop/acceptance/auth.spec.js:140:34")


def test_tests_failing_the_same_way_are_printed_once_and_the_rest_one_line_each():
    from app.agents.lean_fixer import failures_once

    names = ["[AC-1] signs up", "[AC-1] refuses a second name", "[AC-1] refuses a second address", "[AC-1] signs in"]
    output = "\n\n".join([f"{names[0]}:\n" + _SAME.format(line=27, slug="a"),
                          f"{names[1]}:\n" + _SAME.format(line=53, slug="b"),
                          f"{names[2]}:\n" + _SAME.format(line=78, slug="c"),
                          f"{names[3]}:\n" + _OTHER])
    observed = {"command": "the acceptance suite's last run: " + ", ".join(names), "output": output,
                "title": "What its failing tests printed"}

    shown = failures_once(observed)["output"]

    assert shown.count("Received: 500") == 3  # once whole, once in each of the two lines
    assert shown.count("auth.spec.js:27:29") == 1 and "Received: 429" in shown
    assert "- [AC-1] refuses a second name (at auth.spec.js:53):" in shown
    assert "- [AC-1] refuses a second address (at auth.spec.js:78):" in shown
    assert len(shown) < len(output)
    assert not BANNED.search(shown.replace(output, ""))


def test_tests_failing_in_different_ways_are_each_printed_whole():
    from app.agents.lean_fixer import failures_once

    names = ["[AC-1] signs up", "[AC-1] signs in"]
    output = f"{names[0]}:\n" + _SAME.format(line=27, slug="a") + f"\n\n{names[1]}:\n" + _OTHER
    observed = {"command": "the acceptance suite's last run: " + ", ".join(names), "output": output}

    assert failures_once(observed) == observed


# --- the opening's size ------------------------------------------------------------------------------------------

def test_a_fixer_s_target_leaves_room_for_its_framing_within_half_its_summary_trigger(monkeypatch):
    """A 91,776-token slot with 32,000 held for the reply is summarised from 43,020 tokens, 129,060 characters."""
    from app.agents.request_budget import fixer_target, opening_target

    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "91776")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.setenv("SANDBOX_MAX_OUTPUT", "5000")

    # Half of 129,060 characters, less 27,000 of system prompt and tool descriptions.
    assert fixer_target(None, 27_000) == 37_530
    # Every other stage's target is as it was: the trigger less ten command outputs.
    assert opening_target(None) == 79_060


def test_past_its_target_a_fix_request_drops_the_sections_that_do_not_bear_on_its_defect_first():
    from app.agents.lean_fixer import bearing_on
    from app.agents.request_budget import EVIDENCE, STANDING, Part, fit

    evidence = Part(EVIDENCE, "--- Defect ---\n[AC-1] Sign up answers 500.\n")
    bears = "--- The product's API ---\nPOST /api/register creates an account.\n" + "x" * 2_000 + "\n"
    does_not = "--- What later sprints build ---\nAC-7: reports.\n" + "y" * 1_000 + "\n"
    touches = bearing_on(["shop/app/routes/auth.py"], ["/api/register"], ["AC-1"])

    fitted = fit([evidence, Part(STANDING, bears + does_not)], target=2_900, touches=touches)

    assert "POST /api/register creates an account." in fitted.text
    assert "AC-7: reports." not in fitted.text


def test_a_fixer_s_request_prints_each_way_its_tests_failed_once(tmp_path, monkeypatch):
    import json

    import the_fix_stage

    from app.acceptance import suite

    names = ["[AC-1] signs up", "[AC-1] refuses a second name", "[AC-1] refuses a second address"]
    path = tmp_path / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "criteria": {"AC-1": {"id": "AC-1", "text": "Sign up", "status": "failed",
        "tests": [{"name": name, "outcome": "failed", "message": _SAME.format(line=27 + 25 * n, slug=n)}
                  for n, name in enumerate(names)]}}}))
    defect = the_fix_stage.a_defect("[AC-1] Sign up - the acceptance suite says this does not work yet.")

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, defect), real_brief=True)

    request = seen.requests[0]
    assert request.count("Expected: 201\n    Received: 500") == 1
    assert "- [AC-1] refuses a second name (at auth.spec.js:52):" in request
    assert "- [AC-1] refuses a second address (at auth.spec.js:77):" in request
