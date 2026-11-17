"""The role prompts agree with the tools and schemas the roles have, and no two of a role's rules pull apart (LR.54).

Found in a pass over every role's rendered system prompt, after the four of LF.967:
- every writer was told "Write each file once" beside "replace `write_artifact` a whole file, again" and "fixing
  errors iteratively";
- the builders were told to start the service with `run_terminal_command`, the backend specialist "verify the service
  starts without crashing" - and that tool refuses every command that keeps running;
- the security reviewer was told never to raise unasked-for work as "a blocking or major finding", in a scale whose
  words are critical and high (both gate a sprint); the architecture reviewer to record it "as a suggestion", in a
  scale whose word for one is informational;
- the reviewers that must never open the product's files to decide what a test expects were also told to read what
  the files they are pointed at "lead to" - and a test leads to the product module it imports;
- the interface specialist on a plain stack was told there is "nothing to install", beside the rule to install what
  the suite needs in the test-only scope;
- a builder that writes the code was told to explain it in "inline comments you propose";
- the technical lead was told the testing specialist "is the only role told which runner this run's stack chose",
  while every specialist's request names the stack's testing framework.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from tests.test_prompt_names_only_offered_tools import rendered  # noqa: F401 - the fixture

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_a_writer_is_not_told_to_write_each_file_only_once(rendered) -> None:  # noqa: F811
    writers = {name: prompt for name, (prompt, offered) in rendered.items() if "write_artifact" in offered}
    assert writers
    for name, prompt in writers.items():
        flat = _flat(prompt)
        assert "`write_artifact` a whole file, again" in flat, name
        assert "Write each file once" not in flat, name
        assert "never write a file again only to confirm it" in flat, name


def test_no_builder_is_sent_to_start_a_service_the_tool_refuses(rendered, tmp_path) -> None:  # noqa: F811
    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed, match="runs until it is stopped"):
        validate_command(["npm", "start"], "backend_specialist", tmp_path)
    builders = {name: prompt for name, (prompt, offered) in rendered.items() if "run_terminal_command" in offered}
    assert builders
    for name, prompt in builders.items():
        flat = _flat(prompt)
        assert "build it, start it, or test it" not in flat, name
        assert "starts without crashing" not in flat, name
        assert "the tool refuses a command that keeps running" in flat, name


def test_each_reviewer_is_told_which_of_its_own_words_a_suggestion_is(rendered) -> None:  # noqa: F811
    from app.agents.architecture_reviewer import ArchitectureReviewFinding
    from app.agents.security_reviewer import SecurityFinding
    from app.graph.workflow import _GATING_SEVERITIES

    security = _flat(rendered["security_reviewer"][0])
    assert "never as a blocking or major finding" in security  # the shared scope rule
    assert {"critical", "high"} <= _GATING_SEVERITIES
    assert "suggestion" not in SecurityFinding.model_fields["severity"].annotation.__args__
    assert "Here critical and high are blocking and major findings, and a suggestion is info." in security

    architecture = _flat(rendered["senior_architect_reviewer"][0])
    assert "Record that as a suggestion" in architecture
    assert "suggestion" not in ArchitectureReviewFinding.model_fields["severity"].annotation.__args__
    assert "informational is this review's word for a suggestion" in architecture


def test_a_reviewer_kept_out_of_the_product_is_not_led_into_it(rendered) -> None:  # noqa: F811
    led = [name for name, (prompt, _) in rendered.items() if "and what they lead to" in _flat(prompt)]
    kept_out = [name for name, (prompt, _) in rendered.items()
                if re.search(r"never open (?:its|the product's) files", _flat(prompt), re.I)]
    assert {"acceptance_reviewer", "suite_dispute"} <= set(kept_out)
    for name in kept_out:
        assert name not in led or "even one a test imports" in _flat(rendered[name][0]), name


def test_the_interface_specialist_s_no_install_rule_leaves_the_tests_theirs(rendered) -> None:  # noqa: F811
    flat = _flat(rendered["specialist_ui_ux"][0])
    assert "install what the suite needs in the test-only scope" in flat
    assert "there is nothing to install or compile" not in flat
    assert "a test-only install is the tests', not the product's" in flat


def test_a_builder_explains_its_code_in_the_code_it_writes(rendered) -> None:  # noqa: F811
    for name, (prompt, offered) in rendered.items():
        if "write_artifact" in offered:
            assert "inline comments you propose" not in prompt, name
            assert "comments in the code you write" in _flat(prompt), name


def test_the_lead_is_not_told_only_the_testing_role_knows_the_runner(rendered) -> None:  # noqa: F811
    from app.agents.specialists import build_specialist_task_request

    stack = SimpleNamespace(language="Lang", framework="", frontend_framework="", database="",
                            testing_framework="RunnerOfChoice", additional_tools=[])
    request = build_specialist_task_request("Build the store", ["AC-1"], "/nowhere", stack)
    assert "RunnerOfChoice" in request["messages"][-1]["content"]
    assert "only role told which runner" not in _flat(rendered["technical_lead"][0])


NEW_WORDS = (
    "A successful write is saved: never write a file again only to confirm it.",
    "and compile, fixing errors iteratively; prove the service starts by running its tests, as the tool refuses a "
    "command that keeps running.",
    "to build it, test it, or run a program that exits by itself (a service is proven by its tests: the tool refuses "
    "a command that keeps running)",
    "comments in the code you write or in your `documentation` field.",
    "the product has nothing to install or compile, and adding either contradicts the stack; a test-only install is "
    "the tests', not the product's.",
    "Here critical and high are blocking and major findings, and a suggestion is info.",
    "informational is this review's word for a suggestion.",
    "even one a test imports",
)


def test_the_new_words_ban_the_product_s_nouns(rendered) -> None:  # noqa: F811
    every = " ".join(_flat(prompt) for prompt, _ in rendered.values())
    for words in NEW_WORDS:
        assert words in every, words
        assert not BANNED.search(words), words
