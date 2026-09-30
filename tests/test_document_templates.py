"""Every workflow document comes from a fixed template, whatever model wrote it.

The operator's requirement: "create a template for all the documents that will
be produced by the agents, so that even if the model being used changes the
resulting document doesn't change". A model supplies the content of each
section; the template decides which sections exist, their order, their
headings, the labels inside a record and what an empty section says.

Three properties are checked here:

1. every document the workflow writes has a template;
2. every field of every schema - nested records included - is placed in its
   template, so a field added to a schema cannot silently drop out;
3. the heading skeleton is identical for empty, full and oddly-formatted
   content - the variation a different model produces.
"""
from __future__ import annotations

import re
import types
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import pytest
from pydantic import BaseModel

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
from app.agents.principal_architect import ArchitectureDecisionRecord, TechnicalSpecificationOutput
from app.agents.product_manager import ProductManagerOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from app.agents.security_reviewer import SecurityFinding, SecurityReviewOutput
from app.agents.stack_selector import StackSelectorOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.agents.tools_models import TechnologyChoice, TechnologyStack, ToolsAndModelsOutput
from app.analysis.document_manifest import RENDERED_STEMS
from app.doc_templates import TEMPLATE_DIR, render_document, template_names

#: template -> the schema it renders, and the name the template calls it by.
TOP_LEVEL: dict[str, tuple[type[BaseModel], str]] = {
    "product_intake": (ProductManagerOutput, "o"),
    "tools_and_models": (ToolsAndModelsOutput, "o"),
    "technology_stack": (StackSelectorOutput, "o"),
    "technical_specification": (TechnicalSpecificationOutput, "o"),
    "architecture_review": (ArchitectureReviewOutput, "o"),
    "sprint_plan": (SprintPlanOutput, "o"),
    "milestone_plan": (MilestonePlanOutput, "o"),
    "security_review": (SecurityReviewOutput, "o"),
    "milestone_review": (MilestoneReviewOutput, "o"),
}

#: Nested records: template -> [(schema, name)].
NESTED: dict[str, list[tuple[type[BaseModel], str]]] = {
    "tools_and_models": [(TechnologyChoice, "opt")],
    "_stack": [(TechnologyStack, "stack")],
    "technical_specification": [(ArchitectureDecisionRecord, "adr")],
    "architecture_review": [(ArchitectureReviewFinding, "f")],
    "sprint_plan": [(SprintDefinition, "s")],
    "milestone_plan": [(SpecialistTask, "t")],
    "security_review": [(SecurityFinding, "f")],
    "milestone_review": [(MilestoneReviewFinding, "f")],
}


def _source(name: str) -> str:
    return (TEMPLATE_DIR / f"{name}.md.j2").read_text(encoding="utf-8")


def test_every_document_the_workflow_writes_has_a_template():
    names = set(template_names())
    missing = sorted(RENDERED_STEMS - names)
    assert not missing, f"documents with no template: {missing}"
    assert {"sprint_summary", "stage_summary"} <= names


@pytest.mark.parametrize("name", sorted(set(TOP_LEVEL) | set(NESTED)))
def test_every_schema_field_is_placed_in_its_template(name):
    source = _source(name)
    schemas = ([TOP_LEVEL[name]] if name in TOP_LEVEL else []) + NESTED.get(name, [])
    for schema, var in schemas:
        for field in schema.model_fields:
            # `technology_stack` is placed through the shared `_stack` include.
            if re.search(rf"\b{var}\.{field}\b", source):
                continue
            pytest.fail(f"{name}.md.j2 never places {schema.__name__}.{field} (as {var}.{field})")


# --- Instances: empty, full, and the untidy content another model writes ---------

def _value(annotation: Any, mode: str) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        real = [a for a in args if a is not type(None)]
        if mode == "empty" and type(None) in args:
            return None
        return _value(real[0], mode)
    if origin is Literal:
        return args[0]
    if origin in (list, typing.List):
        if mode == "empty":
            return []
        item = args[0] if args else str
        return [_value(item, mode), _value(item, mode)]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _instance(annotation, mode)
    if annotation is bool:
        return mode != "empty"
    if annotation in (int, float):
        return 1
    return {
        "empty": "",
        "full": "A plain sentence of content.",
        # What a different model tends to send: stray whitespace, extra blank
        # lines, a list written inside a prose field, JSON in a string.
        "untidy": "  First line.\n\n\n\n- a dash item\n- another  \n",
    }[mode]


def _instance(schema: type[BaseModel], mode: str) -> BaseModel:
    values = {name: _value(field.annotation, mode) for name, field in schema.model_fields.items()}
    return schema.model_construct(**values)


def _render(name: str, mode: str) -> str:
    schema, _ = TOP_LEVEL[name]
    o = _instance(schema, mode)
    extra: dict[str, Any] = {}
    if name in {"architecture_review", "security_review", "milestone_review"}:
        extra["findings"] = list(getattr(o, "findings", []) or [])
    if name == "milestone_review":
        extra["milestone_goal"] = "" if mode == "empty" else "Goal"
    if name == "technical_specification":
        extra["product_name"] = "" if mode == "empty" else "Product"
    return render_document(name, o=o, **extra)


def _skeleton(text: str) -> list[str]:
    """The fixed headings: level 1 and 2, with any value after ':' or ' — ' cut."""
    out = []
    for line in text.splitlines():
        if re.match(r"^#{1,2} ", line):
            out.append(re.split(r":| — ", line, maxsplit=1)[0].strip())
    return out


@pytest.mark.parametrize("name", sorted(TOP_LEVEL))
def test_the_skeleton_does_not_depend_on_the_content(name):
    empty, full, untidy = (_skeleton(_render(name, mode)) for mode in ("empty", "full", "untidy"))
    assert empty == full == untidy
    assert len(full) >= 2


@pytest.mark.parametrize("name", sorted(TOP_LEVEL))
def test_an_empty_section_says_so(name):
    text = _render(name, "empty")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^## ", line) or line.startswith("## Status"):
            continue
        following = next((l for l in lines[index + 1:] if l.strip()), "")
        assert not following.startswith("#"), f"{name}: '{line}' is empty with no placeholder"


@pytest.mark.parametrize("name", sorted(TOP_LEVEL))
def test_untidy_content_does_not_leave_runs_of_blank_lines(name):
    text = _render(name, "untidy")
    assert "\n\n\n" not in text
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_a_work_order_reads_with_the_same_labels_every_time():
    text = _render("milestone_plan", "full")
    for label in ("**Task:**", "**Files:**", "**Interfaces:**", "**Steps:**", "**Edge cases:**",
                  "**Test cases:**", "**Verification:**", "**Out of scope:**", "**Acceptance criteria:**"):
        assert text.count(label) == 2, label  # two work orders, each labelled


def test_the_sprint_record_keeps_every_line_the_sprint_panel_parses():
    from app.agents.sprint_summary import render_sprint_summary

    text = render_sprint_summary(
        sprint_number=1, total_sprints=2, goal="Goal", planned=["one"],
        attempts=[{
            "number": 1, "status": "Completed", "cases": {"tests": 3, "passed": 3, "failed": 0},
            "rounds": 1, "features": ["Add an item"],
            "defects": [{"status": "fixed", "description": "Empty value accepted", "owner": "backend"}],
            "defect_log": [{"id": "D1", "severity": "major", "state": "fixed", "description": "x",
                            "owner": "backend", "reproduction": "r", "expected": "e", "actual": "a",
                            "files": ["app/x"], "verified_by": "npm test", "regression_test": "t"}],
            "findings": [{"round": 1, "source": "milestone", "severity": "minor",
                          "description": "d", "disposition": "carried to sprint 2"}],
            "carried_forward": ["d"], "lessons": ["l"],
        }],
    )
    assert text.startswith("# Sprint 1 of 2 Summary\n")
    for label in ("**Goal:** Goal", "**Status:** Completed", "**Attempts:** 1", "**Test Cases:** 3",
                  "- **Passed:** 3", "- **Failed:** 0", "## Planned for This Sprint",
                  "## Features Implemented", "- **Rounds Completed:** 1", "- **Total Bugs Found:** 1",
                  "- **Bugs Fixed:** 1", "- **Bugs Open:** 0", "### Defect Summary",
                  "- [FIXED] Empty value accepted (Owner: backend)"):
        assert label in text, label
    # The panel reads defect lines from "Defect Summary" to the end of the file,
    # so nothing after it may look like one.
    after = text.split("### Defect Summary", 1)[1]
    defect_lines = [l for l in after.splitlines() if re.match(r"^- \[(\w+)\] (.+?) \(Owner: (.+?)\)$", l)]
    assert defect_lines == ["- [FIXED] Empty value accepted (Owner: backend)"]
    for heading in ("## Work Orders", "## Defect Log", "## Review Findings", "## Carried Forward",
                    "## Lessons for the Next Sprint"):
        assert heading in text


def test_the_workflow_writes_no_document_without_a_template():
    """`render_artifact` stays as a utility, but nothing in the workflow uses it."""
    source = Path("src/app/graph/workflow.py").read_text(encoding="utf-8")
    assert "render_artifact(" not in source
