"""Every role's system prompt, rendered as the role is built, carries no known contradiction and no rule twice.

Deep review 2026-11-18, item C7: system prompts of 15-19k characters still shipped three contradictions - every role
was given both an "IF YOU ARE REVIEWING" and an "IF YOU ARE BUILDING OR TESTING" line; builders were told "there is no
shell, `cd`/`&&` do not work" beside a terminal tool that runs commands (and takes a leading `cd`); and every builder,
a backend one on any stack included, was told code talking to PostgreSQL by name cannot be tested. Each role is built
here with its real prompt and the prompt it ends with is linted.
"""
from __future__ import annotations

import collections
import re

import pytest

#: Pairs of statements one prompt must not make together.
CONTRADICTIONS = [
    (r"IF YOU ARE REVIEWING", r"IF YOU ARE BUILDING"),
    (r"\bThere is no shell\b", r"`run_terminal_command`"),
    (r"\bdo not work and `cd`", r"`run_terminal_command`"),
    (r"\bShell commands\b", r"`run_terminal_command`"),
]
#: Database servers named by product; a role prompt is generic and gets the stack's own names from its guidance.
STACK_NAMES = ("PostgreSQL", "MySQL", "MongoDB", "Redis", "SQL Server")
#: The roles whose job is to name a stack.
CHOOSES_A_STACK = {"stack_selector", "tools_models_architect"}
#: A sentence this long or longer said twice in one prompt is a duplicated rule.
SHORTEST_RULE = 60


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """{role name: the system prompt it is built with}, for every role."""
    from deepagents import create_deep_agent

    import app.agents.role_agent as role_agent
    from app.models import CompatibleChatOpenAI
    from tests.test_prompt_names_only_offered_tools import _builders

    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    root = tmp_path_factory.mktemp("repo")
    captured: dict[str, str] = {}

    def spy(**kwargs):
        captured[kwargs["name"]] = kwargs["system_prompt"]
        return create_deep_agent(**kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(role_agent, "create_deep_agent", spy)
        patch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
        for build in _builders():
            build(model=model, repo_root=root)
    return captured


def test_every_role_is_rendered(rendered):
    assert len(rendered) >= 15


def test_no_role_prompt_makes_both_statements_of_a_known_contradiction(rendered):
    found = {
        name: [(a, b) for a, b in CONTRADICTIONS if re.search(a, prompt) and re.search(b, prompt)]
        for name, prompt in rendered.items()
    }
    assert {name: pairs for name, pairs in found.items() if pairs} == {}


def test_no_role_prompt_says_one_rule_twice(rendered):
    def twice(prompt: str) -> list[str]:
        flat = " ".join(prompt.split())
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", flat) if len(s) >= SHORTEST_RULE]
        return [s for s, n in collections.Counter(sentences).items() if n > 1]

    assert {name: said for name, prompt in rendered.items() if (said := twice(prompt))} == {}


def test_a_role_that_does_not_choose_the_stack_names_no_database_server(rendered):
    named = {
        name: [server for server in STACK_NAMES if server in prompt]
        for name, prompt in rendered.items() if name not in CHOOSES_A_STACK
    }
    assert {name: servers for name, servers in named.items() if servers} == {}


def test_a_builder_is_given_the_building_half_and_a_reviewer_the_reviewing_half(rendered):
    assert "install what the suite needs in the test-only scope" in " ".join(rendered["specialist_backend"].split())
    assert "BLOCKING finding" in rendered["senior_architect_reviewer"]
    assert "BLOCKING finding" not in rendered["specialist_backend"]


def test_the_new_rule_text_avoids_the_banned_words():
    from app.agents import testing_dependency_rule as rule
    from app.agents.specialists import _system_prompt

    banned = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    shell_line = _system_prompt("backend").split("with no shell", 1)[1].split("rather than trying", 1)[0]
    for text in (rule.TESTING_DEPENDENCY_RULE, rule.FOR_A_REVIEWER, rule.FOR_A_DESIGNER, rule.FOR_A_BUILDER, shell_line):
        assert not set(re.findall(r"[\w-]+", text.lower())) & banned
