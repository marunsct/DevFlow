"""What the run set aside on the way reaches the run's verdict, not only a sprint's record.

An escalation's open issues and the review findings fast delivery records as
risks instead of fixing were written into each sprint's record and never into
`completion_gaps`, so a run that carried them still read as plain
"completed". And the checks that read the files ran at each milestone review
but not at release, where later fixes may have broken what they passed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import delivery


@pytest.fixture
def release(tmp_path, monkeypatch):
    from app.analysis import integration_checks

    found: list[str] = []
    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": found)

    def run(**state):
        update = delivery.release(
            {"repository": SimpleNamespace(root_path=str(tmp_path)), **state},
            {"configurable": {}},
            SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(tmp_path), allow_subdirectories=True),
        )
        return [str(gap) for gap in update.get("completion_gaps") or []]

    run.found = found
    return run


def test_an_escalation_s_open_issue_is_a_gap(release) -> None:
    gaps = release(known_issues=["Design review left open: the export endpoint has no auth"])
    assert any("the export endpoint has no auth" in gap for gap in gaps)


def test_findings_recorded_as_risks_are_a_gap(release) -> None:
    decision = {
        "id": "DR-4",
        "decision": delivery.RECORDED_AS_RISKS,
        "rationale": "Fast delivery. The open findings are carried:\n- [major] deleting a note leaves it listed",
    }
    gaps = release(decisions=[decision])
    assert any("DR-4" in gap and "deleting a note leaves it listed" in gap for gap in gaps)


def test_the_files_are_read_again_at_release(release) -> None:
    release.found.append("index.html links styles.css, which does not exist")
    gaps = release()
    assert any("styles.css, which does not exist" in gap for gap in gaps)


def test_the_fast_path_records_its_risks_under_the_decision_release_reads() -> None:
    import inspect

    from app.graph import workflow

    assert "decision=RECORDED_AS_RISKS" in inspect.getsource(workflow)
