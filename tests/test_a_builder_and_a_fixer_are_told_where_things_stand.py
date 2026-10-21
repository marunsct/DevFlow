"""A builder and a fixer are told where the sprint stands, from what the harness measured (plan PH.1).

Each visit found out what the sprint had done by reading - the finished work
orders, their decisions, the last measurement. The harness holds all of it.
Behind `WHERE_THINGS_STAND`, off until measured.
"""
from __future__ import annotations

import inspect
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.agents import where_things_stand
from app.agents.specialists import SpecialistOutput

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _state(tmp_path):
    return {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "ci_report": "Unit tests: 12 of 14 pass; acceptance tests: 5 of 11 pass.",
        "specialist_outputs": {
            "specialist_backend_0": SpecialistOutput(changed_files=["tasks-api/tasks_api/db.py"],
                                                     decisions=["Items are stored per owner with an index on owner_id"],
                                                     blockers=["The token format is open"]),
            "specialist_backend_1": SpecialistOutput(changed_files=["tasks-api/tasks_api/main.py"]),
        },
    }


def test_off_the_request_is_as_it_was(tmp_path):
    request = {"messages": [{"role": "user", "content": "Build it."}]}
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": ""}):
        assert where_things_stand.with_it(request, _state(tmp_path))["messages"][-1]["content"] == "Build it."


def test_on_the_request_opens_with_the_sprint_s_state_and_leaves_its_own_stage_out(tmp_path):
    request = {"messages": [{"role": "user", "content": "Build it."}]}
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on"}):
        text = where_things_stand.with_it(request, _state(tmp_path), leave_out="specialist_backend_1")["messages"][-1]["content"]

    assert text.startswith(where_things_stand.HEADING) and text.rstrip().endswith("Build it.")
    assert "`tasks-api/tasks_api/db.py`" in text and "index on owner_id" in text and "token format is open" in text
    assert "main.py" not in text and "12 of 14 pass" in text
    assert len(text) - len("Build it.") <= where_things_stand.MOST_CHARACTERS + 2
    fixed = [where_things_stand.HEADING, "Finished this sprint:", "Left open by them:", "The last CI gate",
             "The acceptance suite last measured", "criteria passing", "failing:"]
    assert not any(BANNED.search(words) for words in fixed)


def test_both_requests_carry_it():
    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    assert source.count("where_things_stand.with_it(request, state") == 3
