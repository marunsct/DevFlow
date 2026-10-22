"""A fix request and a work order get their files' neighbours from the harness's code graph (plans CG.1-CG.3).

Fixers and builders found who imports a file, what it imports and which tests
reach it by reading. Behind `PROJECT_GRAPH_FIXES` and `PROJECT_GRAPH_BUILDERS`,
off until measured.
"""
from __future__ import annotations

import re

import inspect
import json
import os
from pathlib import Path
from unittest import mock

from app.analysis import project_graph


def _project(root: Path) -> None:
    (root / ".project-directory").write_text("notes-api")
    p = root / "notes-api"
    (p / "notes_api").mkdir(parents=True)
    (p / "acceptance").mkdir()
    (p / "notes_api" / "__init__.py").write_text("")
    (p / "notes_api" / "store.py").write_text("def save(note):\n    pass\n\ndef load(id):\n    pass\n")
    (p / "notes_api" / "main.py").write_text("from notes_api.store import save, load\n\ndef create():\n    save(1)\n")
    (p / "acceptance" / "test_api.py").write_text("from notes_api.store import load\n\ndef test_ac3_fetches_a_note():\n    load(1)\n")
    (root / ".harness").mkdir()
    (root / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))


def test_the_graph_holds_imports_both_ways_definitions_and_the_criteria_tests_carry(tmp_path):
    _project(tmp_path)

    graph = project_graph.build(tmp_path)

    store = graph["notes-api/notes_api/store.py"]
    assert store["defines"] == ["load", "save"]
    assert set(store["imported_by"]) == {"notes-api/notes_api/main.py", "notes-api/acceptance/test_api.py"}
    assert graph["notes-api/acceptance/test_api.py"]["criteria"] == ["AC-3"]
    assert (tmp_path / project_graph.GRAPH_FILE).is_file()
    # Never in a commit, a digest or the reviewer's diff.
    assert project_graph.GRAPH_FILE.startswith(".harness/") and not (tmp_path / ".project-graph.json").exists()


def test_a_fix_request_gets_the_neighbourhood_only_when_on(tmp_path):
    _project(tmp_path)
    request = lambda: {"messages": [{"role": "user", "content": "Fix it."}]}

    with mock.patch.dict(os.environ, {"PROJECT_GRAPH_FIXES": "on"}):
        on = project_graph.with_the_neighbourhood(request(), tmp_path, ["notes-api/notes_api/store.py"])["messages"][-1]["content"]
    with mock.patch.dict(os.environ, {"PROJECT_GRAPH_FIXES": ""}):
        off = project_graph.with_the_neighbourhood(request(), tmp_path, ["notes-api/notes_api/store.py"])["messages"][-1]["content"]

    assert project_graph.FIX_HEADING in on and "defines load, save" in on
    assert "imported by" in on and "tested by `notes-api/acceptance/test_api.py` (AC-3)" in on
    assert len(on) - len("Fix it.") <= project_graph.MOST_CHARACTERS + 4
    assert off == "Fix it."


def test_both_builder_paths_and_the_fix_request_carry_it():
    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    assert source.count("project_graph.with_the_slice(") == 2 and source.count("project_graph.with_the_neighbourhood(") == 1


def test_a_name_the_graph_does_not_show_is_not_said_to_be_defined_nowhere(tmp_path):
    """The graph reads some languages only; an empty answer read as absent invited a second definition."""
    _project(tmp_path)
    answer = project_graph.build_tool(tmp_path).invoke({"where_is_name": "NotInTheGraph"})
    assert answer["defined_in"] == [] and "Search the files" in answer["note"]
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", answer["note"], re.I)
