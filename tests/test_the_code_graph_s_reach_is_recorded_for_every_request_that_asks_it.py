"""What the code graph named for each request that asked it is recorded, and `loop.sh effects` reads it (plan KG.1).

Measured: `docs/measuring.md` listed `PROJECT_GRAPH_FIXES` and `PROJECT_GRAPH_BUILDERS` as "no signal", so nobody knew
how often a request got a neighbourhood at all; the graph follows imports in two language families only, so a fix in
any other language was expected to get none. One record per request that asked the graph (files, edges and tests by
language, whether a neighbourhood was carried), a firing signal for both switches, and an effects line with the empty
share by language and how each fixer was localised. A record: no request changes.
"""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from app.analysis import project_graph
from app.graph import localised_fix
from app.observability import switch_firing
from app.observability.transcript import asked_for, read_transcript

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
RUN = "run-graph-reach"


def _project(root: Path) -> None:
    """A Python service whose store is imported by its routes and an acceptance test, beside one Go file."""
    (root / ".project-directory").write_text("notes-api")
    p = root / "notes-api"
    (p / "notes_api").mkdir(parents=True)
    (p / "acceptance").mkdir()
    (p / "worker").mkdir()
    (p / "notes_api" / "__init__.py").write_text("")
    (p / "notes_api" / "store.py").write_text("def save(note):\n    pass\n")
    (p / "notes_api" / "main.py").write_text("from notes_api.store import save\n\ndef create():\n    save(1)\n")
    (p / "acceptance" / "test_api.py").write_text("from notes_api.store import save\n\ndef test_ac3_saves():\n    save(1)\n")
    (p / "worker" / "queue.go").write_text("package worker\n\nimport \"notes/store\"\n\nfunc Drain() {\n}\n")
    (root / ".harness").mkdir()
    (root / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))


@pytest.fixture
def a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PROJECT_GRAPH_FIXES", "on")
    monkeypatch.setenv("PROJECT_GRAPH_BUILDERS", "on")
    root = tmp_path / "workspace"
    root.mkdir()
    _project(root)
    return root


def _request() -> dict:
    return {"messages": [{"role": "user", "content": "Fix it."}]}


def _reach() -> list[dict]:
    return read_transcript(RUN, {"project_graph_reach"})


def test_a_fix_request_records_the_edges_and_tests_the_graph_named_by_language(a_run):
    with asked_for("defect_fix_1_0", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/store.py",
                                                                "notes-api/worker/queue.go"])

    [record] = _reach()
    assert record["stage"] == "defect_fix_1_0" and record["purpose"] == "fix" and record["carried"] is True
    assert record["languages"]["python"] == {"files": 1, "held": 1, "edges": 2, "tests": 1}
    # Go: its definitions are read, its imports are not.
    assert record["languages"]["go"] == {"files": 1, "held": 1, "edges": 0, "tests": 0}


def test_a_request_that_carried_a_neighbourhood_fires_its_switch(a_run):
    with asked_for("defect_fix_1_0", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/store.py"])
    with asked_for("implementation_1", RUN):
        project_graph.with_the_slice(_request(), a_run, ["notes-api/notes_api/main.py"])

    assert {"PROJECT_GRAPH_FIXES", "PROJECT_GRAPH_BUILDERS"} <= set(switch_firing.fired(_reach()))


def test_a_request_the_graph_says_nothing_of_is_recorded_without_firing_its_switch(a_run):
    with asked_for("defect_fix_1_0", RUN):
        sent = project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/README.md"])

    [record] = _reach()
    assert sent["messages"][-1]["content"] == "Fix it."
    assert record["carried"] is False and record["languages"] == {
        project_graph.NO_FILE: {"files": 0, "held": 0, "edges": 0, "tests": 0}}
    assert "PROJECT_GRAPH_FIXES" not in switch_firing.fired(_reach())


def test_files_of_no_language_are_not_counted_by_language(a_run):
    """LF.1536: the effects line read "txt 7 of 7" and "json 2 of 2" beside the languages the graph reads - files no
    language reads, counted as if the graph had failed them."""
    for name in ("notes.txt", "data.json"):
        (a_run / "notes-api" / name).write_text("{}\n")
    with asked_for("defect_fix_1_0", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/store.py", "notes-api/notes.txt",
                                                                "notes-api/data.json"])

    [record] = _reach()
    assert set(record["languages"]) == {"python"}


def test_a_request_built_again_on_a_resume_is_recorded_once(a_run):
    for _ in range(3):
        with asked_for("defect_fix_1_0", RUN):
            project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/store.py"])

    assert len(_reach()) == 1


def test_effects_reports_the_empty_share_by_language_and_how_fixers_were_localised(a_run):
    with asked_for("defect_fix_1_0", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/store.py"])
    with asked_for("defect_fix_1_1", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/worker/queue.go"])
    with asked_for("defect_fix_1_2", RUN):
        project_graph.with_the_neighbourhood(_request(), a_run, ["notes-api/notes_api/main.py",
                                                                "notes-api/worker/queue.go"])
    with asked_for("defect_fix_1_0", RUN):
        localised_fix.noted("defect_fix_1_0", localised_fix.Localised(found=["notes-api/notes_api/main.py"],
                                                                      how="route"))
    with asked_for("defect_fix_1_1", RUN):
        localised_fix.noted("defect_fix_1_1", localised_fix.Localised())

    report = "\n".join(runpy.run_path(str(SCRIPT))["effects"](read_transcript(RUN), ""))

    fixes = next(line for line in report.splitlines() if "KG.1 fix requests" in line)
    assert fixes.split()[0] == "3" and "go 2 of 2 (100%)" in fixes and "python 0 of 2 (0%)" in fixes
    assert "KG.1 work orders' requests that asked the code graph: not reached" in report
    localised = next(line for line in report.splitlines() if "fixers localised" in line)
    assert localised.split()[0] == "2" and "route 1" in localised and "none 1" in localised
