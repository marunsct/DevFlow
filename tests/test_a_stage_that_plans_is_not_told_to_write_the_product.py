"""A stage that plans the product is told where it lives, not to write it.

The code-writing stages are told to run `ls` and write into the project
directory. Told that, one run's architect on a local model took itself to be
writing the product and spent its attempts listing an empty directory.
"""

from __future__ import annotations

import re

import pytest

from app.agents import principal_architect, project_layout, scrum_master, technical_lead

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_planning_note_names_the_directory_and_writes_nothing():
    note = project_layout.PLANNED_PROJECT_DIRECTORY

    assert "ONE project directory" in note and "lowercase-with-hyphens" in note
    assert "Run `ls`" not in note and "writes none of the product's files" in note
    assert not BANNED.search(note)


def _the_workspace_and_the_brief():
    from app.documents import DocumentContent
    from app.state import RepositoryContext

    return (RepositoryContext(root_path="/w", branch="main", commit="abc", status="clean"),
            DocumentContent(source_path="brief.md", source_type="markdown", text="Notes.", truncated=False))


def _architecture():
    return principal_architect.build_architecture_request("intake", "tools", "stack", *_the_workspace_and_the_brief())


def _architecture_revision():
    return principal_architect.build_architecture_revision_request(
        "spec", ["name the routes"], "intake", "tools", "stack", *_the_workspace_and_the_brief())


@pytest.mark.parametrize("request_of", [
    _architecture,
    _architecture_revision,
    lambda: technical_lead.build_milestone_planning_request("plan", "Users can keep notes", "/w"),
    lambda: scrum_master.build_sprint_planning_request("spec", "/w"),
], ids=["architect", "architect's revision", "technical lead", "sprint planner"])
def test_each_planning_stage_is_told_where_the_product_lives_and_not_to_write_it(request_of):
    told = "\n".join(str(message["content"]) for message in request_of()["messages"])

    assert "ONE project directory" in told and "writes none of the product's files" in told
    assert "Run `ls` FIRST" not in told
