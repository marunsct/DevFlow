"""The code review checks the data and service bars where the batch's files touch them (PQ.9, cause C4).

Measured on the 2026-11-25 product-quality audit's stored products: a 500 for a forbidden or duplicate request, a filter
accepted and ignored, an error shape that differed by route, none of the constraints, indexes or owner columns the
specification adopted - and the code reviewer was told to raise nothing no criterion asks for, and was never shown the
specification's records or errors to compare with.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from app.agents.code_reviewer import CodeReviewOutput, build_code_review_request, the_standards

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPECIFICATION = SimpleNamespace(
    domain_model=["Note: id uuid, owner_id references User (delete cascade), title required; index on owner_id"],
    error_catalogue=['Every error answers {"error": {"code", "message"}}'],
    api_and_event_contracts=["DELETE /notes/{id} -> 204; 404 when there is none; 403 when it is another user's"],
)


def test_the_reviewer_is_told_the_bars() -> None:
    from app.agents import code_reviewer

    prompt = code_reviewer._SYSTEM_PROMPT
    for bar in ("one error shape", "not found (404)", "forbidden (403)", "server error (500)", "its owner",
                "accepted and then ignored", "constraints and indexes"):
        assert bar in prompt, bar
    assert "at most three" in prompt


def test_the_review_request_carries_what_the_specification_adopted() -> None:
    content = build_code_review_request("diff", "orders", "criteria", "ci", standards=the_standards(SPECIFICATION))[
        "messages"][0]["content"]

    assert "index on owner_id" in content
    assert '{"error": {"code", "message"}}' in content
    assert "403 when it is another user's" in content


def test_the_code_review_stage_hands_the_reviewer_the_specification(tmp_path, monkeypatch) -> None:
    from app import ci
    from app.graph import engineering
    from app.tools.version_control import initialise_repository

    initialise_repository(tmp_path)
    (tmp_path / "server.js").write_text("export const a = 1;\n")
    first = ci.commit(tmp_path, "first")
    ci.save(tmp_path, ci.Snapshot(label="accepted", commit=first), accepted=True)
    (tmp_path / "server.js").write_text("export const a = 2;\n")
    ci.commit(tmp_path, "batch")
    seen: list[str] = []

    def gated(state, config, **kwargs):
        seen.append(kwargs["initial_request"]["messages"][0]["content"])
        return {kwargs["output_key"]: CodeReviewOutput(approved=True), "stage": "code_review"}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", gated)
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    state: dict[str, Any] = {"repository": SimpleNamespace(root_path=str(tmp_path)), "review_defects": [],
                             "technical_specification": SPECIFICATION}

    engineering.code_review(state, {"configurable": {"thread_id": "t"}}, SimpleNamespace(
        judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True))

    assert "index on owner_id" in seen[0]


def test_bar_findings_are_bounded_and_the_most_severe_kept() -> None:
    bar = {"work_order": "w", "file": "a.py", "quality_bar": True}
    review = CodeReviewOutput.model_validate({"approved": False, "findings": [
        {**bar, "severity": "minor", "problem": "list has no bound"},
        {**bar, "severity": "major", "problem": "deleting another user's note answers 500"},
        {**bar, "severity": "minor", "problem": "no index on title"},
        {**bar, "severity": "major", "problem": "the status filter is accepted and ignored"},
        {**bar, "severity": "minor", "problem": "two error shapes"},
        {"work_order": "w", "severity": "minor", "problem": "a work order half done"},
    ]})

    problems = [f.problem for f in review.findings]

    assert len([f for f in review.findings if f.quality_bar]) == 3
    assert "deleting another user's note answers 500" in problems
    assert "the status filter is accepted and ignored" in problems
    assert "a work order half done" in problems


def test_the_bars_use_none_of_the_banned_words() -> None:
    from app.agents.code_reviewer import QUALITY_BARS

    described = str(CodeReviewOutput.model_json_schema())
    assert not [text for text in (QUALITY_BARS, the_standards(SPECIFICATION), described) if BANNED.search(text)]
