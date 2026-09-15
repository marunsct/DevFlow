"""Seven agents produced their work twice. Now they produce it once.

Each wrote a document to `docs/` *and* returned the same content as the
structured response the pipeline routes on, generated separately from one
understanding with nothing reconciling them. Measured costs:

- Divergence: run-0b55ad49 left a 1 KB `docs/spec.md` beside a 51 KB
  `docs/technical_specification.md`; the reviewer read the thin one and blocked
  a sprint over detail that was in the other file.
- Double generation: the specification is ~40 KB of prose, asked for twice.
- Confusion about "done": run-0edfcd33's architect wrote the document, then
  reported in prose on three fresh conversations, each ~100,000 characters, and
  the run failed. From its side the schema was redundant - it had delivered.
"""

from __future__ import annotations

import pytest

from app.agents.artifact_document import render_artifact

#: Every agent whose document is now generated rather than written.
GENERATED = [
    ("product_manager", "docs/product_intake.md"),
    ("tools_models", "docs/tools_and_models.md"),
    ("scrum_master", "docs/sprint_plan.md"),
    ("technical_lead", "docs/milestone_plan.md"),
]


def _intake():
    from app.agents.product_manager import ProductManagerOutput

    return ProductManagerOutput(
        product_name="To-Do App",
        users_and_stakeholders=["End users"],
        core_workflows=["Add a task", "Delete a task"],
        constraints=["No external dependencies"],
    )


def test_a_flat_schema_becomes_sections():
    document = render_artifact(_intake(), title="Product Intake")

    assert document.startswith("# Product Intake — To-Do App")
    assert "## Core workflows" in document
    assert "- Add a task" in document
    assert "- No external dependencies" in document


def test_the_naming_field_becomes_the_title_not_a_section():
    document = render_artifact(_intake(), title="Product Intake")

    assert "## Product name" not in document


def test_an_empty_section_says_so():
    """A gap a reviewer should notice is not the same as a gap that is hidden."""
    assert "_Not specified._" in render_artifact(_intake(), title="Product Intake")


def test_nested_records_render_with_a_readable_heading():
    """Seven tasks must not become seven headings that all say "backend"."""
    from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask

    plan = MilestonePlanOutput(
        selected_sprint_goal="Sprint 1",
        delegated_tasks=[
            SpecialistTask(
                specialist_role="backend",
                task_description="Build the storage layer",
                acceptance_criteria=["Persists to localStorage"],
            )
        ],
    )

    document = render_artifact(plan, title="Milestone Plan")

    assert "#### backend — Build the storage layer" in document
    assert "**Acceptance criteria:**" in document
    assert "- Persists to localStorage" in document
    # The fields promoted into the heading must not repeat below it.
    assert "**Task description:**" not in document


def test_every_schema_field_reaches_the_document():
    """A field with nowhere to go is content silently dropped."""
    from app.agents.product_manager import ProductManagerOutput

    document = render_artifact(_intake(), title="Product Intake")

    for field in ProductManagerOutput.model_fields:
        if field == "product_name":
            continue
        heading = field.replace("_", " ").strip().capitalize().lower()
        assert heading in document.lower() or field.replace("_", " ") in document.lower(), field


def test_the_document_says_where_it_came_from():
    document = render_artifact(_intake(), title="Product Intake")

    assert "Generated from this stage's structured response" in document


@pytest.mark.parametrize(("agent", "path"), GENERATED)
def test_the_agent_is_not_told_to_write_it(agent, path):
    module = __import__(f"app.agents.{agent}", fromlist=["_SYSTEM_PROMPT"])
    flat = " ".join(module._SYSTEM_PROMPT.split())

    assert "Do not write a document" in flat, agent
    assert f"Write exactly one artifact, at `{path}`" not in flat


@pytest.mark.parametrize(("agent", "path"), GENERATED)
def test_the_workflow_renders_it(agent, path):
    from pathlib import Path

    workflow = (Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py").read_text()

    assert f'"{path}"' in workflow, f"{path} is no longer written by anyone"


def test_no_agent_both_writes_and_returns_the_same_artifact():
    """The pattern this replaced, pinned so it cannot come back."""
    from pathlib import Path

    directory = Path(__file__).resolve().parent.parent / "src/app/agents"
    offenders = []
    for path in directory.glob("*.py"):
        text = path.read_text()
        if "response_format" not in text and "_SYSTEM_PROMPT" not in text:
            continue
        if "Write exactly one artifact" in text or "Write your intake artifact" in text:
            offenders.append(path.stem)

    assert not offenders, f"still asked to write a document they also return: {offenders}"


def test_json_stuffed_into_a_prose_field_is_unpacked():
    """Models put structure into string fields; the content is right, the
    container is wrong.

    Measured on run-78804673: the architect's `product_scope` - a prose field -
    arrived as `{"in_scope": [...], "deferred_scope": [...]}`, and rendering it
    verbatim produced a single 1,200-character line no reader would read.
    """
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.specification_document import render_specification

    spec = TechnicalSpecificationOutput(
        product_scope='{"in_scope": ["Add a task"], "deferred_scope": ["User accounts"]}'
    )

    document = render_specification(spec, "To-Do")

    assert "**In scope:**" in document
    assert "- Add a task" in document
    assert "**Deferred scope:**" in document
    assert '{"in_scope"' not in document, "the raw blob must not survive"


def test_a_json_array_in_a_prose_field_becomes_a_list():
    from app.agents.artifact_document import _value_lines

    assert _value_lines('["one", "two"]') == ["- one", "- two"]


def test_ordinary_prose_is_left_exactly_alone():
    """Only text that parses as JSON is touched."""
    from app.agents.artifact_document import _value_lines

    prose = "A single-page to-do list. Uses localStorage {no server}."

    assert _value_lines(prose) == [prose]


def test_text_that_merely_starts_with_a_brace_is_not_mangled():
    from app.agents.artifact_document import _value_lines

    text = "{this is not json, just prose that opens with a brace"

    assert _value_lines(text) == [text]


def test_both_renderers_share_one_behaviour():
    """The spec renderer delegates, so a fix in one is a fix in both."""
    from app.agents.artifact_document import _value_lines
    from app.agents.specification_document import _as_lines

    payload = '{"a": ["x"]}'

    assert _as_lines(payload) == _value_lines(payload)


# --- the invariant, not the instances ------------------------------------
#
# This mistake was made three times in one session, each time by fixing where
# the symptom appeared rather than the class it belonged to:
#
#   1. the scope rule went to five stages and missed the scrum master
#   2. the stack went into one of three sprint-loop request builders
#   3. `can_write=False` went to the two reviewers, and the five agents
#      converted to generated documents afterwards kept their write tool
#
# The third cost run-78804673, which failed at `technical_lead`: "asked to
# write the same thing 5 times in a row... The repeated request was:
# docs/milestone_plan.md". Told not to write, still holding the tool, no cue
# for when to stop - exactly what the architecture reviewer had done hours
# earlier.
#
# A test over the whole directory is the only version of this fix that cannot
# be applied to six of seven places.


def test_no_agent_is_told_not_to_write_while_holding_a_write_tool():
    from pathlib import Path

    directory = Path(__file__).resolve().parent.parent / "src/app/agents"
    offenders = []
    for path in sorted(directory.glob("*.py")):
        source = path.read_text()
        # Only agents - modules that construct one. `role_agent` is the factory
        # that defines `can_write`, and its own comments quote the instruction
        # while explaining why it exists.
        if "create_role_agent(" not in source or path.stem == "role_agent":
            continue
        if "Do not write a" in source and "can_write=False" not in source:
            offenders.append(path.stem)

    assert not offenders, (
        "told not to write a document but still given write_artifact: "
        f"{offenders}. An agent with a tool it is told not to use will use it - "
        "take the tool away instead."
    )


def test_agents_that_do_write_code_keep_their_tools():
    """The specialists build the product; removing their tools would be absurd."""
    import inspect

    from app.agents import specialists

    assert "can_write=False" not in inspect.getsource(specialists)


def test_a_read_only_agent_is_not_told_how_to_write():
    """Contradictory instructions cost a stage.

    Measured on run-db3a4a0b: the scrum master - whose document the workflow
    now renders - received "CRITICAL DIRECTORY RULES: Write all document
    artifacts ... inside `docs/`" alongside its own "Do not write a document".
    It went looking for the tool and reported "I don't have a `write_artifact`
    tool or any file-writing/editing tools available" instead of returning its
    structured response.
    """
    from app.agents.role_agent import _READ_ONLY_RULES, _WRITING_RULES

    assert "write_artifact" in _WRITING_RULES
    assert "write_artifact" not in _READ_ONLY_RULES
    assert "CRITICAL DIRECTORY RULES" not in _READ_ONLY_RULES

    flat = " ".join(_READ_ONLY_RULES.split())
    assert "You have no file-writing or editing tools, and need none" in flat
    assert "do not report that one is missing" in flat


def test_the_rules_follow_the_tools():
    """Whichever half an agent gets must match what it actually holds."""
    import inspect

    from app.agents.role_agent import create_role_agent

    source = inspect.getsource(create_role_agent)

    assert "_WRITING_RULES if can_write else _READ_ONLY_RULES" in source


def test_a_writing_agent_still_gets_the_directory_rules():
    """The specialists build the product and need every word of this."""
    from app.agents.role_agent import _WRITING_RULES

    assert "CRITICAL DIRECTORY RULES" in _WRITING_RULES
    assert "ONE top-level project folder" in _WRITING_RULES


def test_no_agent_writes_a_document_the_workflow_also_renders():
    """The instance-versus-class mistake, caught a fourth time.

    `test_no_agent_is_told_not_to_write_while_holding_a_write_tool` only finds
    an agent whose prompt says "Do not write a". The stack selector's did not
    say it, so the test passed while the stage held a write tool and wrote
    `docs/technology_stack.md` itself. On run-0b18e403 it printed its selection
    into the conversation, wrote the document, printed it again, wrote again -
    five identical writes, and the repeat guard ended the run at stage three.

    The class is: if the workflow renders a document, the agent that produced
    its content must not be able to write one too. That is checkable from the
    two sides together.
    """
    import inspect
    import re
    from pathlib import Path

    from app.graph import workflow

    rendered = set(re.findall(r'"(docs/[a-z0-9_]+\.md)"', inspect.getsource(workflow)))
    assert rendered, "expected the workflow to render some documents"

    directory = Path(__file__).resolve().parent.parent / "src/app/agents"
    offenders = []
    for path in sorted(directory.glob("*.py")):
        source = path.read_text()
        if "create_role_agent(" not in source or path.stem == "role_agent":
            continue
        if "can_write=False" in source:
            continue
        # Which rendered document, if any, belongs to this agent's stage?
        stage = re.search(r'_STAGE\s*=\s*"([^"]+)"', source)
        if not stage:
            continue
        for document in rendered:
            stem = Path(document).stem
            if stem in source and "specialist" not in path.stem:
                offenders.append(f"{path.stem} still writes {document}")

    assert not offenders, (
        "the workflow renders these documents, so the agent must not hold a "
        f"write tool: {offenders}"
    )
