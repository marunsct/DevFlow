"""A gating design finding resolved on a sentence about how a library or the test setup behaves is not plainly
resolved (LF.1440).

Measured on a medium run (deep review 2026-11-25, decisions finding 1): in review round 6 three of the last six gating
findings were resolved on the re-review's word about a sentence of the specification - "SQLAlchemy maps ARRAY columns
to JSON type ... The ORM layer handles this transparently" (false: the tables could not be created on SQLite), "each
acceptance test runs in its own Playwright worker process with a separate SQLite file" (the harness starts the product
once for the suite). Sprint 1 then took 9 h 53 min for 8 -> 9 of 21 tests with both blockers in the code. The
specification, the stack and the re-review's answers are the run's own.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.agents.architecture_reviewer import (
    EARLIER_FINDINGS_RULE, ArchitectureReviewFinding, ArchitectureReviewOutput, EarlierFindingAnswer)
from app.graph import design_gate
from app.graph.workflow import _format_finding

SPECIFICATION = (Path(__file__).parent / "captured" / "technical-specification-a-medium-brief.md").read_text()
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = {
    "framework": "FastAPI", "frontend_framework": "React on Vite", "database": "PostgreSQL",
    "testing_framework": "Vitest for unit tests of the page, pytest for unit tests of the service, Playwright for "
                         "acceptance tests",
    "additional_tools": ["SQLAlchemy (async ORM)", "Alembic (migrations)", "python-jose (JWT)",
                         "passlib (password hashing)", "Pydantic (validation)", "httpx (async HTTP testing)",
                         "Vite (frontend build)", "Docker Compose (orchestration)"],
}
G16 = ArchitectureReviewFinding(
    severity="major",
    description="ARRAY column type (categories, tags) is not addressed for SQLite compatibility. The domain model "
                "(line 15) defines categories and tags as ARRAY<VARCHAR(100)>. SQLite does not support native ARRAY "
                "types.",
    evidence="Tests run on SQLite (line 84); production uses PostgreSQL.",
    required_remediation="Add a note in ADR-05 or the domain model explaining how ARRAY columns are handled in "
                         "SQLite - or replace ARRAY with a JSON column type that is consistent across both databases.")
G17 = ArchitectureReviewFinding(
    severity="major",
    description="Database reset mechanism between acceptance tests is not specified. The acceptance suite starts the "
                "service once.",
    evidence="Testing section line 99.",
    required_remediation="Specify the database reset mechanism in the testing section.")
ROUND_6 = {
    1: "Domain model line 22: 'ARRAY column compatibility: The Task model's categories and tags columns use "
       "SQLAlchemy's ARRAY type. In PostgreSQL, these are stored as native ARRAY<VARCHAR(100)>. In SQLite (used for "
       "development and testing), SQLAlchemy maps ARRAY columns to JSON type, storing values as JSON arrays. The ORM "
       "layer handles this transparently — reads and writes work identically in both databases.'",
    2: "Testing section line 100: 'Database reset between acceptance tests: each acceptance test runs in its own "
       "Playwright worker process with a separate SQLite file. The acceptance suite's playwright.config.js assigns a "
       "unique DATA_DIR per worker (e.g., 'data/worker-0/', 'data/worker-1/') via the workerId property, so each "
       "worker gets a fresh database file.'",
}


def _round_6(tmp_path: Path, answers: dict[int, str]) -> tuple[dict, dict]:
    previous = ArchitectureReviewOutput(status="changes_required", findings=[G16, G17])
    state = {
        "architecture_review": previous,
        "technical_specification": SPECIFICATION,
        "stack_selection": SimpleNamespace(technology_stack=STACK),
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        design_gate.KEY: {"round": 5, "findings": [
            {"number": 16, "source": design_gate.REVIEWER, "text": _format_finding(G16), "raised": 5,
             "status": "open", "finding": G16.model_dump()},
            {"number": 17, "source": design_gate.REVIEWER, "text": _format_finding(G17), "raised": 5,
             "status": "open", "finding": G17.model_dump()},
        ]},
    }
    review = ArchitectureReviewOutput(status="approved", findings=[], earlier_findings=[
        EarlierFindingAnswer(number=number, resolved=True, where=where) for number, where in answers.items()])
    update: dict = {}
    after = design_gate.after_a_review(state, update, review, {}, [])
    return update, {"review": after, "state": state}


def test_a_resolution_resting_on_how_a_library_behaves_is_a_claim_to_verify(tmp_path):
    update, _ = _round_6(tmp_path, {1: ROUND_6[1]})

    g16 = next(entry for entry in update[design_gate.KEY]["findings"] if entry["number"] == 16)
    assert g16["status"] == "resolved"
    assert "SQLAlchemy" in g16["assumption"]["rests_on"]
    assert "maps ARRAY columns to JSON type" in g16["assumption"]["claim"]
    # What the lead and every builder read with the specification's rulings.
    from app.agents.specification_rulings import the_rulings_section

    section = the_rulings_section(tmp_path)
    assert "G16" in section and "SQLAlchemy maps ARRAY columns to JSON type" in section


def test_a_resolution_resting_on_how_the_harness_runs_the_suite_is_refused(tmp_path):
    update, seen = _round_6(tmp_path, {2: ROUND_6[2]})

    g17 = next(entry for entry in update[design_gate.KEY]["findings"] if entry["number"] == 17)
    assert g17["status"] == "open"
    assert seen["review"].status == "changes_required"


def test_a_resolution_that_quotes_nothing_of_the_specification_is_not_one(tmp_path):
    update, _ = _round_6(tmp_path, {1: "The specification now covers this in the domain model."})

    g16 = next(entry for entry in update[design_gate.KEY]["findings"] if entry["number"] == 16)
    assert g16["status"] == "open"


def test_the_words_the_reviewer_and_the_builders_read_use_no_banned_word(tmp_path):
    _round_6(tmp_path, {1: ROUND_6[1]})

    assert not BANNED.search(EARLIER_FINDINGS_RULE)
    assert not BANNED.search(design_gate.the_claims_section(tmp_path).split("\n- ")[0])
