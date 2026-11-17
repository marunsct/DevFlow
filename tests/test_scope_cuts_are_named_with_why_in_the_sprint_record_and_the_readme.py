"""Each criterion a sprint or a release goes on without is named with why, in the Sprint Record and the README (LR.42).

The Sprint Record's status line listed deferred ids with no reason, and a criterion still failing when an escalation
accepted the sprint as it stood was named nowhere in it; the README a stranger reads named no cut at all, so a product
shipped without a criterion read as the whole brief delivered.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.agents.sprint_summary import render_sprint_summary
from app.graph import workflow
from app.sprint import record
from app.stacks import release_docs

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def test_a_deferred_criterion_and_one_accepted_failing_are_cut_with_why():
    cuts = record.scope_cuts(
        ["AC-4"], {"AC-4": "could not be made to pass after fixes and re-planning (timeout)"},
        failing=[{"id": "AC-4", "status": "failed"}, {"id": "CR-1", "status": "failed"}],
        accepted_at_escalation="accept the sprint with its open problems recorded as known issues",
    )
    assert [cut["id"] for cut in cuts] == ["AC-4", "CR-1"]
    assert "re-planning (timeout)" in cuts[0]["why"]
    assert "escalation accepted the sprint" in cuts[1]["why"]
    # Not accepted at an escalation: a failing criterion is not a cut, the sprint is planned again.
    assert record.scope_cuts([], {}, failing=[{"id": "AC-2", "status": "failed"}]) == []


def test_the_sprint_record_has_a_scope_cuts_section_only_when_something_was_cut():
    attempt = {"number": 1, "status": "Completed", "deferred": ["AC-4"], "rounds": 1,
               "scope_cuts": [{"id": "AC-4", "why": "could not be made to pass after fixes and re-planning"}]}
    text = render_sprint_summary(sprint_number=2, total_sprints=3, goal="Search", planned=["Search"],
                                 attempts=[attempt])
    assert "## Scope cuts" in text
    assert "- AC-4: could not be made to pass after fixes and re-planning" in text
    section = text.split("## Scope cuts", 1)[1].split("\n## ", 1)[0]
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", section, re.IGNORECASE), word
    plain = render_sprint_summary(sprint_number=2, total_sprints=3, goal="Search", planned=["Search"],
                                  attempts=[{**attempt, "deferred": [], "scope_cuts": []}])
    assert "## Scope cuts" not in plain


def test_the_workflow_records_the_cuts_of_an_accepted_sprint(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "deferred", lambda root: {"AC-4": "could not be made to pass (timeout)"})
    from app.graph import acceptance_nodes

    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "CR-1", "status": "failed"}], ""))
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    cuts = workflow._the_scope_cuts(state, ["AC-4"], "accept the sprint as it stands")
    assert [cut["id"] for cut in cuts] == ["AC-4", "CR-1"]
    assert workflow._the_scope_cuts(state, [], "") == []


def _locked(root, criteria):
    path = root / suite.STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"criteria": [{"id": cid, "text": text, "source": "brief"} for cid, text in criteria]}))


def test_the_readme_names_each_cut_with_its_criterion_and_why_and_drops_the_section_when_none(tmp_path):
    (tmp_path / "README.md").write_text("# Notes\n\nRun it with `make run`.\n\n## Usage\n\nSee below.\n")
    _locked(tmp_path, [("AC-3", "Notes can be exported as CSV."), ("AC-10", "Search finds notes by tag.")])
    written = release_docs.name_the_scope_cuts(tmp_path, {"AC-10": "could not be made to pass", "AC-3": "deferred"})
    assert written == ["README.md"]
    text = (tmp_path / "README.md").read_text()
    assert "## Scope cuts" in text and "## Usage" in text and "Run it with `make run`." in text
    assert "- **AC-3** (Notes can be exported as CSV.): deferred" in text
    assert text.index("**AC-3**") < text.index("**AC-10**")
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", text.split("## Scope cuts", 1)[1], re.IGNORECASE), word
    # A later release rewrites the section, not adds a second one; nothing cut removes it.
    release_docs.name_the_scope_cuts(tmp_path, {"AC-3": "deferred"})
    assert (tmp_path / "README.md").read_text().count("## Scope cuts") == 1
    assert "AC-10" not in (tmp_path / "README.md").read_text()
    release_docs.name_the_scope_cuts(tmp_path, {})
    assert "## Scope cuts" not in (tmp_path / "README.md").read_text()
    assert "## Usage" in (tmp_path / "README.md").read_text()


def test_the_release_names_the_cuts_in_the_readme():
    import inspect

    from app.graph import delivery

    assert "release_docs.name_the_scope_cuts(root," in inspect.getsource(delivery.release)
