"""A finished run is "non-deliverable" only for what means the product may not work.

Measured on nine finished runs: all nine were marked non-deliverable, five of them at full hidden marks, so the mark
said nothing. What only a reader should know now stays beside it as a note, and a kind of gap nobody listed still
blocks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import junit, suite
from app.acceptance.criteria import number
from app.graph import delivery, terminal_state
from app.handover.test_documents import acceptance_test_document
from app.server.events import EventBus
from app.server.runner import WorkflowRunner

NOTES = [
    "2 locked test(s) were reclassified under dispute: test_a, test_b",
    "The suite was locked with this still open: a test reads a page before it opens it.",
    "The locked suite did not notice the product changed: `src/a.py` line 3, `False` made `True`, and every test that passed still passed.",
    "No test holds the product to a behaviour a deliberate change showed: `src/a.py` line 3.",
    "6 line(s) of the interface contract were not checked at release: GET /a/{id} -> 200 (a route with a parameter in it)",
    "2 write line(s) of the interface contract were not asked with an unparsable body: POST /a",
    "The product ships no unit tests: its unit test command ran none and exited as a pass.",
    "No review read the product's code: every sprint was accepted on its locked suite alone.",
    "The plan was dispatched with this noted against it: two parts name one file.",
    "Design review finding settled by DR-7: [blocking] the specification contradicts itself.",
    "An escalation left this open: Design review finding settled by DR-7: [blocking] the specification contradicts itself.",
    "An escalation left this open: Design review left open: [major] one sentence is unclear.",
    "An escalation left this open: The sprint plan is one sprint for every criterion, written by the harness: no answer",
    "A milestone review's findings were recorded as risks, not fixed (DR-15): [major] accessibility: a list holds a paragraph.",
    "Code the product does not run: `backend/` repeats files nothing serves.",
    "Ships 1 dependency under a strong-copyleft licence, which binds the product's own licence: a (see `LICENCES.md`).",
    "The judgement model 'm' could not be built (ValueError), so the architect, QA, reviews, test rounds and fixes run on the default model.",
]

BLOCKING = [
    "No acceptance suite was locked; the milestone reviews were the only gate.",
    "AC-14 ships deferred, unproven by the suite: nothing starts the service.",
    "14 of the project's own unit tests still fail and ship failing (the locked acceptance suite passes): a; b.",
    "The project setup was never proven: `stack-setup.json` cannot be used.",
    "`app/README.md` says nowhere how to run the product: name the commands that install, start and test it.",
    "The project has no README: someone who did not write it cannot tell how to install it.",
    "`app/config.py` line 3 holds a key: a credential must come from the environment.",
    "At release the product does not keep its interface contract: contract 6: DELETE /a/{id} -> 400",
    "At release, reading the files still finds: the page calls a route no server has.",
    "The interface contract's checks could not run at release: their runner wrote no report.",
    "Adding the release files failed: disk full",
    "A milestone review's findings were recorded as risks, not fixed (DR-20): [blocking] correctness: the brief's limit is exceeded.",
    "An escalation left this open: The product is not ready to release - the acceptance suite says: AC-2 failed.",
    # A note's words later in the line do not make it one, and nobody has listed this kind.
    "A kind of gap written after this test: The suite was locked with this still open.",
]


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.redis_client import reset_clients

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


async def _finish(runner, root: Path, gaps: list[str], stage: str = "complete", error: str | None = None) -> Any:
    record = runner.register_run(
        run_id="run-1", thread_id="thread-1", document_names=["brief.md"], document_paths=["/tmp/brief.md"],
        owner="alice", tenant_id="acme",
    )
    record.status = "running"
    record.repo_root = str(root)
    runner.run_store.save(record)
    await runner._handle_state(
        record, SimpleNamespace(invoke=lambda *_: None), {"stage": stage, "completion_gaps": gaps, "error": error}, {}
    )
    return runner.run_store.load("run-1")


def _notes_file(root: Path) -> dict[str, Any]:
    return json.loads((root / "DELIVERY-NOTES.json").read_text(encoding="utf-8"))


async def test_notes_alone_leave_the_product_deliverable_and_every_note_in_view(runner, tmp_path) -> None:
    stored = await _finish(runner, tmp_path, NOTES)

    assert terminal_state.read(tmp_path) is None
    assert _notes_file(tmp_path)["deliverable"] is True
    assert _notes_file(tmp_path)["notes"] == NOTES
    assert stored.completion_gaps == NOTES
    assert stored.status == "completed"


@pytest.mark.parametrize("gap", BLOCKING)
async def test_a_gap_that_may_mean_breakage_is_still_non_deliverable(runner, tmp_path, gap) -> None:
    await _finish(runner, tmp_path, [gap, NOTES[0]])

    marker = terminal_state.read(tmp_path)
    assert marker is not None
    assert marker["deliverable"] is False
    assert marker["completion_gaps"] == [gap]


async def test_the_marker_keeps_its_fields_and_carries_the_notes_beside_them(runner, tmp_path) -> None:
    await _finish(runner, tmp_path, [BLOCKING[0], NOTES[0], NOTES[1]])

    marker = terminal_state.read(tmp_path)
    assert {"deliverable", "status", "reason", "stage", "completion_gaps", "at"} <= set(marker)
    assert marker.get("notes") == [NOTES[0], NOTES[1]]
    assert "1 gap(s)" in marker["reason"]
    assert not (tmp_path / "DELIVERY-NOTES.json").exists()


async def test_a_failed_run_is_non_deliverable_with_notes_alone(runner, tmp_path) -> None:
    await _finish(runner, tmp_path, [NOTES[0]], stage="failed", error="it stopped")

    marker = terminal_state.read(tmp_path)
    assert marker["status"] == "failed"
    assert marker["reason"] == "it stopped"
    assert marker.get("notes") == [NOTES[0]]


async def test_a_clean_release_leaves_neither_file_from_an_earlier_ending(runner, tmp_path) -> None:
    terminal_state.mark(tmp_path, status="failed", reason="an earlier attempt")
    (tmp_path / "DELIVERY-NOTES.json").write_text("{}", encoding="utf-8")

    await _finish(runner, tmp_path, [])

    assert terminal_state.read(tmp_path) is None
    assert not (tmp_path / "DELIVERY-NOTES.json").exists()


# --- what the release writes -----------------------------------------------------------------------------------------

def _released(root: Path, monkeypatch, **state: Any) -> dict[str, Any]:
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    suite.save_criteria(root, number("# Brief\n## Features\n- Add a note\n"))
    target = root / "notes" / "acceptance" / "notes.spec.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("test('[AC-1] adds', ()=>{});\n")
    suite.lock(root)
    (root / ".project-directory").write_text("notes\n")
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds")])
    judged = suite._judged(root, suite.AcceptanceResult(ran=True, command="npm test", report=report), False)
    monkeypatch.setattr(suite, "run", lambda *a, **k: judged)
    return delivery.release(
        {
            "repository": SimpleNamespace(root_path=str(root)),
            "product_intake": SimpleNamespace(product_name="Notes"),
            "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(goal="Notes", criteria=[])]),
            **state,
        },
        {"configurable": {"thread_id": "t"}}, None,
    )


def test_a_settled_finding_is_not_stated_as_open_and_an_open_one_is(tmp_path, monkeypatch) -> None:
    settled = "Design review finding settled by DR-7: [major] two sections disagree."
    still_open = "Design review left open: [major] one sentence is unclear."

    gaps = _released(tmp_path, monkeypatch, known_issues=[settled, still_open])["completion_gaps"]

    assert settled in gaps
    assert f"An escalation left this open: {still_open}" in gaps
    assert not any("left this open" in gap and "settled" in gap for gap in gaps)


def test_a_blocking_finding_past_the_cut_still_reads_as_blocking(tmp_path, monkeypatch) -> None:
    long_finding = "[major] style: " + "words " * 200
    decision = {
        "id": "DR-3", "decision": delivery.RECORDED_AS_RISKS,
        "rationale": f"Fast delivery.\n{long_finding}\n[blocking] correctness: the page never loads.",
    }

    gaps = _released(tmp_path, monkeypatch, decisions=[decision])["completion_gaps"]

    assert any(gap.startswith("A milestone review") and "[blocking] correctness" in gap for gap in gaps)
    assert "words" in " ".join(gaps), "the other finding keeps what room is left"


def test_the_evidence_page_and_the_decision_say_which_is_which(tmp_path, monkeypatch) -> None:
    update = _released(tmp_path, monkeypatch, acceptance_open_problems=["a test reads a page before it opens it"])

    page = (tmp_path / "docs" / "reviews" / "release-evidence.md").read_text(encoding="utf-8")
    assert "## Completion gaps" not in page
    assert "## Notes for the reader" in page
    assert "a test reads a page before it opens it" in page
    assert "may not work" not in update["decisions"][-1]["rationale"]
    assert "a test reads a page before it opens it" in update["decisions"][-1]["rationale"]


def test_the_acceptance_document_keeps_a_note_apart_from_a_gap() -> None:
    page = acceptance_test_document({"completion_gaps": [BLOCKING[1], NOTES[0]]})

    assert "## Notes for the reader" in page
    gaps_part, notes_part = page.split("## Notes for the reader")
    assert BLOCKING[1][:40] in gaps_part
    assert NOTES[0][:40] in notes_part


def test_what_this_adds_for_the_reader_uses_none_of_the_banned_words(tmp_path, monkeypatch) -> None:
    _released(tmp_path, monkeypatch, acceptance_open_problems=["x"])

    page = (tmp_path / "docs" / "reviews" / "release-evidence.md").read_text(encoding="utf-8")
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", page, re.IGNORECASE), word
