"""Three smaller prompts, each behind its own switch, and none changing between two calls of one run.

Per-role audit of 2026-11-20 (items 4, 7 and 8): the acceptance suite's writer and the QA lead heard the stack's
product-code rules ("wrap async route handlers"), lessons learned from fixes and a beginner documentation section;
review roles carried 2.9k-9.7k characters of writer guidance, a command guide without a command tool and those lessons;
a technical lead's re-plan was sent 96k-234k characters, 134k of them project memory. Each cut is in doubt until
measured, so each is off unless switched on, and is read once per run so a server's prompt cache keeps its prefix.
"""
from __future__ import annotations

import json
import re
import uuid

import pytest

from app.plugins.seed import SEED_INSTRUCTIONS
from tests.a_role_agent import Scripted, Stopped

SWITCHES = ("QA_PROMPT_TRIMMED", "REVIEWER_SHAPED_PLUGIN_CONTENT", "LEAD_REPLAN_REQUEST_SMALLER")
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: What a JavaScript page's stack guidance says, by where it comes from.
PRODUCT_RULE = "wrap async route handlers"            # the node module, about the product's code
TEST_RULE = "toBeVisible()"                           # the page-testing notes
SETUP_NOTE = "Install Playwright with `npm i -D @playwright/test`"   # a setup note
HOW_TO_LINE = "Dependency Management: respect a lockfile"            # how to install
COMMAND_GUIDE = "There is no shell: a command is one program."
ANSWER_GUIDE = "Give your answer as one call of your answer tool."
LESSON_FOR_ALL = "Run the whole unit suite before answering."
LESSON_FOR_THE_QA_LEAD = "Name the criterion each finding is about."


class _Store:
    """The plugin store, holding the seed rows and two of the model's guides."""

    rows = {**SEED_INSTRUCTIONS, "guide:one_program_a_command": COMMAND_GUIDE, "guide:answer_in_schema": ANSWER_GUIDE}

    def get_instructions(self, name):
        return self.rows.get(name.lower())

    def get_generated_framework_names(self):
        return set()


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """A workspace whose stack is a JavaScript page, two approved lessons, and every switch unset."""
    from app.plugins import lessons, registry

    for name in (*SWITCHES, "SWITCH_OVERRIDES_FROM_SETTINGS", "STABLE_STAGE_PREFIX"):
        monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setattr(registry.PluginStore, "shared", staticmethod(lambda: _Store()))
    monkeypatch.setattr("app.plugins.middleware._extract_stack_keywords",
                        lambda root: ["javascript", "node", "html", "playwright"])
    monkeypatch.setattr("app.models.model_guidance.guidance_key",
                        lambda: ["guide:one_program_a_command", "guide:answer_in_schema"])
    for role, rule in (("all", LESSON_FOR_ALL), ("acceptance_reviewer", LESSON_FOR_THE_QA_LEAD)):
        lessons.decide(lessons.propose("javascript", f"seen for {role}", rule, 3, role=role)["id"], True)
    root = tmp_path / "work"
    root.mkdir()
    return root


def _suite_writer(model, repo_root):
    from app.agents.specialists import create_specialist_agent

    return create_specialist_agent("testing", model=model, repo_root=repo_root, writing_the_suite=True)


def _builder(model, repo_root):
    from app.agents.specialists import create_specialist_agent

    return create_specialist_agent("backend", model=model, repo_root=repo_root)


def _qa_lead(model, repo_root):
    from app.agents.acceptance_reviewer import create_acceptance_reviewer_agent

    return create_acceptance_reviewer_agent(model=model, repo_root=repo_root)


def _security_reviewer(model, repo_root):
    from app.agents.security_reviewer import create_security_reviewer_agent

    return create_security_reviewer_agent(model=model, repo_root=repo_root)


def _first_request(build, root, run: str = "", stage: str = "probe", request: str = "go"):
    """The messages the agent `build` makes sends its model on its first call, in run `run` and stage `stage`."""
    from app.models.model_pin import as_the_run

    model = Scripted(replies=[], requests=[], offered=[])
    with as_the_run(run or None):  # built inside its run, as a workflow node builds it
        agent = build(model=model, repo_root=str(root))
    configurable = {"thread_id": uuid.uuid4().hex, "app_stage": stage, **({"app_run_id": run} if run else {})}
    with pytest.raises(Stopped):
        agent.invoke({"messages": [{"role": "user", "content": request}]}, {"configurable": configurable})
    return model.requests[0]


def _system_prompt(build, root, **kwargs) -> str:
    return str(_first_request(build, root, **kwargs)[0].content)


# --- QA_PROMPT_TRIMMED -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("build", [_suite_writer, _qa_lead], ids=["suite writer", "QA lead"])
def test_with_the_qa_trim_off_the_suite_roles_hear_what_they_heard_before(stack, monkeypatch, build):
    unset = _system_prompt(build, stack)
    monkeypatch.setenv("QA_PROMPT_TRIMMED", "off")

    assert _system_prompt(build, stack) == unset
    assert all(text in unset for text in (PRODUCT_RULE, TEST_RULE, LESSON_FOR_ALL))


@pytest.mark.parametrize("build", [_suite_writer, _qa_lead], ids=["suite writer", "QA lead"])
def test_with_the_qa_trim_on_the_suite_roles_hear_only_the_stack_guidance_about_tests(stack, monkeypatch, build):
    monkeypatch.setenv("QA_PROMPT_TRIMMED", "on")

    prompt = _system_prompt(build, stack)

    assert PRODUCT_RULE not in prompt and HOW_TO_LINE not in prompt and LESSON_FOR_ALL not in prompt
    assert TEST_RULE in prompt and "Writing JavaScript tests" in prompt and ANSWER_GUIDE in prompt


def test_with_the_qa_trim_on_the_qa_lead_keeps_a_lesson_written_for_it(stack, monkeypatch):
    monkeypatch.setenv("QA_PROMPT_TRIMMED", "on")

    prompt = _system_prompt(_qa_lead, stack)

    assert LESSON_FOR_THE_QA_LEAD in prompt and LESSON_FOR_ALL not in prompt
    assert prompt.startswith("You are the QA lead reviewing an acceptance suite before it is locked.")


def test_with_the_qa_trim_on_the_suite_writer_has_no_beginner_documentation_and_keeps_its_role(stack, monkeypatch):
    monkeypatch.setenv("QA_PROMPT_TRIMMED", "on")

    prompt = _system_prompt(_suite_writer, stack)

    assert "Beginner documentation requirement" not in prompt
    assert "acceptance suite" in prompt and "Constraints:" in prompt and "`run_terminal_command`" in prompt


def test_the_qa_trim_leaves_a_builder_as_it_was(stack, monkeypatch):
    before = _system_prompt(_builder, stack)
    monkeypatch.setenv("QA_PROMPT_TRIMMED", "on")

    after = _system_prompt(_builder, stack)

    assert after == before and "Beginner documentation requirement" in after and PRODUCT_RULE in after


# --- REVIEWER_SHAPED_PLUGIN_CONTENT ------------------------------------------------------------------------------


@pytest.mark.parametrize("build", [_security_reviewer, _qa_lead], ids=["security reviewer", "QA lead"])
def test_with_reviewer_shaping_off_a_reviewer_hears_what_it_heard_before(stack, monkeypatch, build):
    unset = _system_prompt(build, stack)
    monkeypatch.setenv("REVIEWER_SHAPED_PLUGIN_CONTENT", "off")

    assert _system_prompt(build, stack) == unset
    assert all(text in unset for text in (SETUP_NOTE, HOW_TO_LINE, COMMAND_GUIDE, LESSON_FOR_ALL))


@pytest.mark.parametrize("build", [_security_reviewer, _qa_lead], ids=["security reviewer", "QA lead"])
def test_with_reviewer_shaping_on_a_reviewer_hears_no_how_to_setup_command_guide_or_lesson(stack, monkeypatch, build):
    monkeypatch.setenv("REVIEWER_SHAPED_PLUGIN_CONTENT", "on")

    prompt = _system_prompt(build, stack)

    for left_out in (SETUP_NOTE, HOW_TO_LINE, COMMAND_GUIDE, LESSON_FOR_ALL, "--with-deps", "A JUNIT XML REPORT"):
        assert left_out not in prompt, left_out
    assert PRODUCT_RULE in prompt and TEST_RULE in prompt and ANSWER_GUIDE in prompt
    assert prompt.startswith("You are the ")


def test_reviewer_shaping_leaves_a_builder_as_it_was(stack, monkeypatch):
    before = _system_prompt(_builder, stack)
    monkeypatch.setenv("REVIEWER_SHAPED_PLUGIN_CONTENT", "on")

    assert _system_prompt(_builder, stack) == before


# --- Read once per run, and the signal each leaves ----------------------------------------------------------------


@pytest.mark.parametrize("switch,build", [("QA_PROMPT_TRIMMED", _suite_writer),
                                          ("REVIEWER_SHAPED_PLUGIN_CONTENT", _security_reviewer)])
def test_a_switch_set_while_a_run_goes_changes_none_of_that_run_s_prompts(stack, monkeypatch, switch, build):
    run = f"run-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(switch, "on")
    first = _system_prompt(build, stack, run=run)
    monkeypatch.setenv(switch, "off")

    assert _system_prompt(build, stack, run=run) == first
    assert _system_prompt(build, stack, run=f"{run}-next") != first


@pytest.mark.parametrize("switch,build", [("QA_PROMPT_TRIMMED", _qa_lead),
                                          ("REVIEWER_SHAPED_PLUGIN_CONTENT", _security_reviewer)])
def test_a_shaped_prompt_is_recorded_once_for_the_switch_firing_check(stack, monkeypatch, switch, build):
    from app.observability import switch_firing
    from app.observability.transcript import read_transcript

    run = f"run-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(switch, "on")
    _system_prompt(build, stack, run=run)
    _system_prompt(build, stack, run=run)

    records = [r for r in read_transcript(run) if r.get("kind") == "prompt_shaped"]
    assert len(records) == 1 and records[0]["left_out_characters"] > 0
    assert switch_firing.fired(records) == [switch]


# --- LEAD_REPLAN_REQUEST_SMALLER -----------------------------------------------------------------------------------

SPRINT_FILE = "ledger/src/entries.js"
OTHER_FILE = "ledger/src/report.js"
SPECIFICATION = "# Specification\n\n" + "".join(
    f"## Section {n}\n\n" + f"Line {n} of what the product must do.\n" * 120 for n in range(12))


@pytest.fixture
def project(stack):
    """A project with a sprint's own file, another file and a long specification."""
    for path, text in ((SPRINT_FILE, "export function addEntry(entry) {\n  return entry;\n}\n"),
                       (OTHER_FILE, "export function monthlyReport(entries) {\n  return entries.length;\n}\n"),
                       ("docs/technical_specification.md", SPECIFICATION),
                       ("docs/sprint_plan.md", "# Sprint plan\n\n1. Entries.\n2. Reports.\n")):
        target = stack / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return stack


ATTEMPT = {
    "number": 1, "reason": "the acceptance suite still fails", "defects": [],
    "work_orders": [{"title": "Entries", "files_planned": [SPRINT_FILE], "files_changed": [SPRINT_FILE]}],
}


def _lead_request(root, last_attempt=None) -> str:
    from app.agents.technical_lead import build_milestone_planning_request

    return build_milestone_planning_request("1. Entries.\n2. Reports.", "Entries", str(root),
                                            last_attempt=last_attempt)["messages"][0]["content"]


def _lead(model, repo_root):
    from app.agents.technical_lead import create_technical_lead_agent

    return create_technical_lead_agent(model=model, repo_root=repo_root)


def _what_the_lead_reads(root, request: str, run: str = "") -> str:
    return str(_first_request(_lead, root, run=run, stage="technical_lead", request=request)[1].content)


def test_with_the_smaller_replan_off_a_replan_holds_the_whole_project(project, monkeypatch):
    unset = _what_the_lead_reads(project, _lead_request(project, ATTEMPT))
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "off")

    read = _what_the_lead_reads(project, _lead_request(project, ATTEMPT))

    assert read == unset
    assert f"=== {OTHER_FILE} ===" in read and "Line 11 of what the product must do." in read


def test_with_the_smaller_replan_on_a_replan_holds_only_the_sprint_s_files_whole(project, monkeypatch):
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")

    read = _what_the_lead_reads(project, _lead_request(project, ATTEMPT))

    assert f"=== {SPRINT_FILE} ===" in read and "export function addEntry" in read
    assert f"=== {OTHER_FILE} ===" not in read and "monthlyReport" in read, "the other file is named with what it defines"
    assert "docs/technical_specification.md (outline" in read and "Line 11 of what the product must do." not in read
    # The request quotes the sprint plan whole, so the memory names it as there (LF.1566).
    assert "=== docs/sprint_plan.md ===" not in read and "quotes it whole" in read and "docs/sprint_plan.md" in read
    assert "You are now planning the milestone for this sprint: 'Entries'" in read


def test_with_the_smaller_replan_on_a_first_plan_is_as_it_was(project, monkeypatch):
    first = _what_the_lead_reads(project, _lead_request(project))
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")

    assert _what_the_lead_reads(project, _lead_request(project)) == first


def test_a_replan_request_is_the_same_bytes_through_a_run(project, monkeypatch):
    from app.models.model_pin import as_the_run

    run = f"run-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")
    with as_the_run(run):
        first = _lead_request(project, ATTEMPT)
        monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "off")
        again = _lead_request(project, ATTEMPT)

    assert again == first and SPRINT_FILE in first


def test_the_smaller_replan_leaves_its_signal_in_what_the_lead_reads(project, monkeypatch):
    from app.observability import switch_firing

    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")
    read = _what_the_lead_reads(project, _lead_request(project, ATTEMPT))
    record = {"kind": "model_request", "messages": [read]}

    assert switch_firing.fired([record]) == ["LEAD_REPLAN_REQUEST_SMALLER"]
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "off")
    assert switch_firing.fired([{**record, "messages": [_what_the_lead_reads(project, _lead_request(project, ATTEMPT))]}]) == []


def test_what_the_smaller_prompts_say_uses_no_product_word():
    from app.agents import prompt_size

    said = [prompt_size.REPLAN_SAID, prompt_size.sprint_files_section([SPRINT_FILE]), *prompt_size.SAID.values(),
            json.dumps([s.explanation for s in (prompt_size.qa_prompt_trimmed_switch, prompt_size.reviewer_shaped_switch,
                                                 prompt_size.lead_replan_smaller_switch)])]

    assert [BANNED.findall(text) for text in said] == [[] for _ in said]


@pytest.mark.parametrize("budget", [12_000, 240_000], ids=["small window", "large window"])
def test_the_smaller_replan_request_is_never_larger_than_the_one_it_replaces(project, monkeypatch, budget):
    """Measured on a small window: the budget the sliced files freed filled with documents the whole memory had left
    out, and the "smaller" re-plan request grew."""
    for n in range(6):
        (project / f"ledger/src/part_{n}.js").write_text(
            f"export function part{n}(value) {{\n" + f"  value = value + {n};\n" * 200 + "  return value;\n}\n")
    (project / "docs/acceptance_criteria.md").write_text("# Criteria\n\n" + "- AC-1: entries are kept.\n" * 300)
    monkeypatch.setattr("app.agents.project_memory.budget_for", lambda model: budget)
    replaced = len(_what_the_lead_reads(project, _lead_request(project, ATTEMPT)))
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")

    smaller = len(_what_the_lead_reads(project, _lead_request(project, ATTEMPT)))

    assert smaller <= replaced, (smaller, replaced)
