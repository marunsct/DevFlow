"""A stage that plans the product is told where it lives, not to write it.

The code-writing stages are told to run `ls` and write into the project
directory. Told that, one run's architect on a local model took itself to be
writing the product and spent its attempts listing an empty directory.
"""

from __future__ import annotations

import inspect
import re

from app.agents import principal_architect, project_layout, scrum_master, technical_lead

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_planning_note_names_the_directory_and_writes_nothing():
    note = project_layout.PLANNED_PROJECT_DIRECTORY

    assert "ONE project directory" in note and "lowercase-with-hyphens" in note
    assert "Run `ls`" not in note and "writes none of the product's files" in note
    assert not BANNED.search(note)


def test_the_planning_stages_use_it_and_not_the_writing_one():
    for builder in (
        principal_architect.build_architecture_request,
        principal_architect.build_architecture_revision_request,
        technical_lead.build_milestone_planning_request,
        scrum_master.build_sprint_planning_request,
    ):
        source = inspect.getsource(builder)
        assert "PLANNED_PROJECT_DIRECTORY" in source, builder.__name__
        assert "Run `ls` FIRST" not in source, builder.__name__


def test_the_sprint_plan_request_carries_it():
    body = scrum_master.build_sprint_planning_request("spec", "/w")["messages"][0]["content"]

    assert project_layout.PLANNED_PROJECT_DIRECTORY in body and "Run `ls` FIRST" not in body
