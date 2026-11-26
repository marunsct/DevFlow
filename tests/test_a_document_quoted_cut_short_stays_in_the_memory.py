"""A document a request quotes cut short is not taken as quoted whole: the memory keeps it and a read of it reads it
(LF.1573).

Measured on the latest medium run: the architecture review's request quoted the specification under its path's
heading, 41,388 of its 89,083 characters, and said "Use your repository read tools to open the full document if you
need a section that is not shown above"; the memory, reading the heading alone, left the specification out as
"quoted whole" and answered a read of it with a pointer back to the request. The request is that review's, word for
word; the workspace is an architecture review's documents. The lead's sprint plan, cut by its own `_truncate`, is
read through the lead's real request builder.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory, stage_memory

CAPTURED = Path(__file__).parent / "captured"
EXCERPTED = (CAPTURED / "architecture-review-request-specification-excerpted.txt").read_text("utf-8")
ARCHITECTURE = json.loads((CAPTURED / "architecture_review_opening.json").read_text("utf-8"))
SPECIFICATION = "docs/technical_specification.md"


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def test_an_excerpted_specification_is_not_quoted_whole():
    assert SPECIFICATION not in project_memory.quoted_whole_in(EXCERPTED)


def test_a_sprint_plan_the_lead_s_request_cut_short_is_not_quoted_whole(tmp_path):
    from app.agents.technical_lead import build_milestone_planning_request

    long_plan = "\n".join(f"{n}. A sprint goal, with what it builds and why it is there." for n in range(20_000))
    short = build_milestone_planning_request("1. Entries.\n2. Reports.", "Entries", str(tmp_path))
    cut = build_milestone_planning_request(long_plan, "Entries", str(tmp_path))

    assert "docs/sprint_plan.md" in project_memory.quoted_whole_in(short["messages"][0]["content"])
    assert "docs/sprint_plan.md" not in project_memory.quoted_whole_in(cut["messages"][0]["content"])


@pytest.mark.parametrize("document", [
    "# Specification\n\n" + "A line of the specification.\n" * 400,
    "".join(f"## Section {n}\n\n" + "A line of this section.\n" * 40 for n in range(10)),
], ids=["without sections", "with sections"])
def test_a_document_fitted_by_the_excerpt_builder_is_not_quoted_whole(document):
    from app.agents.text_budget import excerpt

    request = f"--- The specification (/{SPECIFICATION}) ---\n{excerpt(document, 2_000, what='the specification')}\n"

    assert project_memory.quoted_whole_in(request) == ()


def test_the_memory_keeps_the_excerpted_specification_and_a_read_of_it_reads_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    for path, text in ARCHITECTURE["files"].items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    (tmp_path / "task-management-dashboard").mkdir()
    sent: list = []
    with stage_memory.remembering("an-excerpted-review"):
        memory = project_memory.build_project_memory_middleware(str(tmp_path))
        memory.wrap_model_call(_Request(messages=[HumanMessage(content=EXCERPTED)], model=None),
                               lambda request: sent.append(request.messages))
        read = memory.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": "/" + SPECIFICATION}}),
            lambda request: ToolMessage(content="the file", tool_call_id="r1"))
    stage_memory.forget_everything()
    text = "\n".join(str(m.content) for m in sent[-1])

    assert f"=== {SPECIFICATION}" in text
    assert read.content == "the file"
