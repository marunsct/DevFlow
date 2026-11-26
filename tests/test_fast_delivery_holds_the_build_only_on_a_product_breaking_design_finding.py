"""In fast delivery a gating design finding holds the build only when it says the product cannot work (LF.1524,
`FAST_DESIGN_GATE_ON_PRODUCT_BREAKING`).

Measured on 135 scored runs: 23 were built with a blocking, critical or major design finding open, and their hidden
score was that of every run - most such findings are about the document. Fast delivery gave every one a single
revision and then built with it open. With the switch on, a finding that the product cannot start in the harness
setup, that a brief requirement is dropped, that one user's data is open to another, or that the contract contradicts
itself on a status code or a field gets a second revision and a review after each; one about the document's form is
recorded as before.
"""
from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput, EarlierFindingAnswer
from app.decisions import render
from app.graph import fast_design_gate

CAPTURED = json.loads((Path(__file__).parent / "captured" / "design-review-gating-findings.json").read_text())["findings"]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _finding(captured: dict) -> ArchitectureReviewFinding:
    return ArchitectureReviewFinding(**{name: captured[name] for name in
                                        ("severity", "evidence", "description", "required_remediation")})


def _captured(kind: str, source: str = "review") -> ArchitectureReviewFinding:
    return _finding(next(item for item in CAPTURED if item["class"] == kind and item["source"] == source))


#: The data folder never made, as one stored review raised it: the product cannot start in the harness setup.
BREAKING = _captured("start")
#: Contract lines in none of the reader's forms, as one stored review raised it: about the document.
DOCUMENT = _finding(next(item for item in CAPTURED if item["description"].startswith("Seven lines")))


@pytest.mark.parametrize("captured", CAPTURED, ids=lambda item: f"{item['class'] or 'not-held'}-{item['source']}")
def test_a_stored_review_s_gating_finding_is_classed_by_what_it_says_of_the_product(captured):
    assert fast_design_gate.product_breaking(_finding(captured), source=captured["source"]) == captured["class"]


@pytest.mark.parametrize("description", [
    # No stored architecture review has raised one yet; worded as the brief that asked for this class says it.
    "Every item route reads the item by its id alone, so any signed-in user can read or delete another user's items.",
    "The list endpoint skips authentication although the brief asks that only a signed-in person sees their list.",
])
def test_a_hole_that_opens_one_user_s_data_to_another_is_product_breaking(description):
    finding = ArchitectureReviewFinding(severity="blocking", description=description, evidence="api_and_event_contracts",
                                        required_remediation="Scope every read and write to the signed-in user.")
    assert fast_design_gate.product_breaking(finding) == fast_design_gate.SECURITY


def _review(status: str, *findings, answers=()) -> ArchitectureReviewOutput:
    return ArchitectureReviewOutput(status=status, findings=list(findings),
                                    earlier_findings=[EarlierFindingAnswer(number=n, resolved=r) for n, r in answers])


def _rounds(tmp_path, monkeypatch, reviews, *, switch="on", one_review="on"):
    """Drive the architecture review of a fast-delivery run through `reviews`, one a round, the state carried between
    them as the graph carries it: [(the update, what the reviewer was asked)] for each round."""
    from workflow_nodes import an_architecture_review

    from app.graph import workflow

    monkeypatch.setenv("FAST_DESIGN_GATE_ON_PRODUCT_BREAKING", switch)
    monkeypatch.setenv("ONE_DESIGN_REVIEW", one_review)
    state = {"architecture_revision_count": 0, "decisions": [], "document": SimpleNamespace(text="Notes over HTTP.")}
    done = []
    for review in reviews:
        update, asked = an_architecture_review(tmp_path, review, state=state, patches={
            "app.graph.workflow._fast_delivery": lambda: True,
            "app.graph.workflow._decided_after_one_revision": workflow._decided_after_one_revision,
        })
        done.append((update, asked))
        state = {**state, **update}
        if update.get("stage") != "principal_architect":
            break
    return done


def test_only_the_product_breaking_finding_holds_and_for_at_most_two_revisions(tmp_path, monkeypatch):
    still = [(1, False), (2, False)]
    rounds = _rounds(tmp_path, monkeypatch, [
        _review("changes_required", BREAKING, DOCUMENT),
        _review("changes_required", BREAKING, DOCUMENT, answers=still),
        _review("changes_required", BREAKING, DOCUMENT, answers=still),
        _review("changes_required", BREAKING, DOCUMENT, answers=still),
    ])

    assert [update["stage"] for update, _ in rounds] == ["principal_architect", "principal_architect", "escalation"]
    # Each revision is reviewed again, since only a review says whether the held finding is resolved.
    assert all(asked for _, asked in rounds)
    last = rounds[-1][0]
    assert last["escalation"]["kind"] == "design"
    held = [d for d in last["decisions"] if "design finding H" in d["question"]]
    assert [d["decision"] for d in held] == [
        "held as product-breaking: sent back for revision 1 of 2",
        "held as product-breaking: sent back for revision 2 of 2",
        "held as product-breaking, still open after 2 revisions: to the design escalation",
    ]
    assert all("H1 " in d["question"] for d in held)
    not_held = [d for d in last["decisions"] if "not held" in d["decision"]]
    assert len(not_held) == 1 and "follow none of the three accepted" in not_held[0]["rationale"]


def test_a_held_finding_the_second_review_finds_resolved_is_recorded_so_and_the_build_starts(tmp_path, monkeypatch):
    rounds = _rounds(tmp_path, monkeypatch, [
        _review("changes_required", BREAKING, DOCUMENT),
        _review("approved", answers=[(1, True), (2, True)]),
    ])

    update, asked = rounds[-1]
    assert asked and update["stage"] == "scaffold"
    assert any(d["decision"] == "held as product-breaking, resolved in review round 2" for d in update["decisions"])


@pytest.mark.parametrize("switch, first", [("off", [BREAKING, DOCUMENT]), ("on", [DOCUMENT])],
                         ids=["switch off", "a document finding alone"])
def test_otherwise_one_revision_is_decided_by_the_gates_as_before(tmp_path, monkeypatch, switch, first):
    rounds = _rounds(tmp_path, monkeypatch, [_review("changes_required", *first), _review("approved")], switch=switch)

    (_, asked_first), (second, asked_second) = rounds
    assert asked_first and asked_second == []
    assert second["stage"] == "scaffold"
    assert not [d for d in second["decisions"] if "design finding H" in d["question"]]


def test_with_a_second_review_a_document_finding_alone_goes_to_the_escalation_after_one_revision(tmp_path, monkeypatch):
    rounds = _rounds(tmp_path, monkeypatch, [_review("changes_required", DOCUMENT),
                                             _review("changes_required", DOCUMENT, answers=[(1, False)])],
                     one_review="off")

    assert [update["stage"] for update, _ in rounds] == ["principal_architect", "escalation"]


def test_the_effects_report_counts_what_was_held_what_was_not_and_the_revisions_spent(tmp_path, monkeypatch):
    still = [(1, False), (2, False)]
    rounds = _rounds(tmp_path, monkeypatch, [_review("changes_required", BREAKING, DOCUMENT)]
                     + [_review("changes_required", BREAKING, DOCUMENT, answers=still)] * 2)

    effects = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py"))["effects"]
    lines = [line for line in effects([], render(rounds[-1][0]["decisions"])) if "LF.1524" in line]

    assert [int(line.split()[0]) for line in lines] == [1, 1, 1]
    assert "0 resolved, 1 to the design escalation" in lines[0]
    assert [line for line in effects([], render([])) if "LF.1524" in line][0].endswith("not reached")


def test_the_words_its_decisions_write_name_no_product_word(tmp_path, monkeypatch):
    still = [(1, False), (2, False)]
    rounds = _rounds(tmp_path, monkeypatch, [_review("changes_required", BREAKING, DOCUMENT)]
                     + [_review("changes_required", BREAKING, DOCUMENT, answers=still)] * 2)
    written = [fast_design_gate.SAID, fast_design_gate.NOT_HELD, fast_design_gate.EXTRA,
               *fast_design_gate.CLASSES.values()]
    for decision in rounds[-1][0]["decisions"]:
        if decision["point"] == "technical_specification" and "design" in decision["question"].lower() + "design":
            # What it writes, without the findings it quotes.
            own = re.split(r"The finding:|Open:|recorded as before:", decision["rationale"])[0]
            written += [decision["question"], decision["decision"], own]
    assert not [text for text in written if BANNED.search(text)]
