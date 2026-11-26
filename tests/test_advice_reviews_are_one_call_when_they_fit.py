"""The specialists' advice reviews of a sprint are one call when their advice fits one request (plan PA.9, the rest).

Measured on a medium run: after a sprint the UI/UX, database, backend and security-and-reliability reviews each opened
with about 32,000 tokens - the same memory, sprint and changed files four times over - to check 6-10 items each.
The items and the answer lines below are the run's own (the database and security reviews' adopted items, and a
security review's answer on another run, with a line that names no item).
"""
from __future__ import annotations

import logging
import re

from app.agents.advice_review import AdviceReview
from app.agents.advice_reviews_together import _SYSTEM_PROMPT, build_request, roles_together, split
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _document, _graph, _milestone, _milestone_review, _repository, _security_review, _specialist, agents, responds_with,
)

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DATABASE = [
    "DB-1: Create a `users` table with columns: id (UUID primary key), email (VARCHAR(255) unique not null), "
    "password_hash (VARCHAR(255) not null), full_name (VARCHAR(100) not null), created_at (TIMESTAMP not null default "
    "now()), and is_active (BOOLEAN not null default true).",
    "DB-2: Create a `refresh_tokens` table with columns: id (UUID primary key), user_id (UUID not null foreign key to "
    "users.id), token (TEXT unique not null), expires_at (TIMESTAMP not null), and created_at (TIMESTAMP not null "
    "default now()).",
]
SECURITY = [
    "SR-5: Implement a global exception handler in FastAPI using @app.exception_handler(Exception) that catches all "
    "unhandled exceptions and returns a JSON response with only an error code and user-facing message, never stack "
    "traces, internal file paths, or database query details.",
    "SR-6: Never include password hashes, refresh tokens, or JWT signing secrets in any API response body, log output, "
    "or error message sent to the client.",
]
#: A security review's answer as it was given, one line naming no item among them.
ANSWERED = [
    "SR-5: http.Server in notes-api/main.go (line 30-33) lacks ReadTimeout, WriteTimeout, and IdleTimeout — should "
    "be 10s, 10s, 120s respectively",
    "SR-6: notes-api/server.go handleCreateNote (line 69) and handleUpdateNote (line 113) do not use "
    "http.MaxBytesReader to limit request body size",
    "Security review: notes-api/main.go line 31 sets Addr to \":\" + port (binds 0.0.0.0) instead of \"127.0.0.1:\" + "
    "port as product intake requires",
]


def test_two_specialists_whose_items_fit_one_request_are_reviewed_together() -> None:
    due = {"database": DATABASE, "security_reliability": SECURITY}

    assert roles_together(due, sees_images=False, domain_review=False, room_characters=20_000) == [
        "database", "security_reliability"]


def test_each_review_stays_its_own_call_when_one_call_cannot_hold_it() -> None:
    due = {"ui_ux": ["UX-1: At mobile width the interface uses a single-column layout."], "database": DATABASE}

    # The UI/UX reviewer is shown the page as screenshots; the database review is then alone.
    assert roles_together(due, sees_images=True, domain_review=False, room_characters=20_000) == []
    # Each role also reviews its own domain, with its own schema.
    assert roles_together(due, sees_images=False, domain_review=True, room_characters=20_000) == []
    # The items together are longer than the room allows.
    assert roles_together(due, sees_images=False, domain_review=False, room_characters=500) == []


def test_the_one_answer_goes_back_to_each_specialist_by_its_item_s_id() -> None:
    answer = AdviceReview(not_built=[*ANSWERED, "DB-2: models.py stores `token` in plain text"])

    found = split(["database", "security_reliability"], answer,
                  {"database": ["DB-1", "DB-2"], "security_reliability": ["SR-5", "SR-6"]})

    assert "[database specialist] not built: DB-2: models.py stores `token` in plain text" in found["database"]
    assert [line.split(": ", 2)[1][:4] for line in found["security_reliability"]] == ["SR-5", "SR-6"]
    # A line naming no item goes to the first of them, so the milestone review still hears it.
    assert found["database"][0].startswith("[database specialist] not built: Security review: notes-api/main.go")


def test_the_request_lists_each_specialist_s_items_under_its_own_heading_and_the_sprint_once() -> None:
    text = build_request(
        {"database": (DATABASE, "the sprint plan places them here"), "security_reliability": (SECURITY, "")},
        "Sign-up and sign-in", "", ["backend/app/models.py"],
    )["messages"][0]["content"]

    assert "--- The database specialist's advice the specification adopted, due now: the sprint plan places" in text
    assert "--- The security and reliability specialist's advice the specification adopted ---" in text
    assert DATABASE[1] in text and SECURITY[0] in text
    assert text.count("--- The sprint just finished ---") == 1 and text.count("backend/app/models.py") == 1


def test_the_new_text_a_model_reads_names_no_product_and_no_control() -> None:
    request = build_request({"database": (["DB-1: an id"], "")}, "", "", [])["messages"][0]["content"]

    assert not BANNED.search(_SYSTEM_PROMPT) and not BANNED.search(request)


def test_through_the_graph_one_call_serves_both_specialists(agents, monkeypatch, tmp_path, caplog) -> None:
    from test_reviews_run_side_by_side import _a_sprint_with_advice_reviews

    monkeypatch.setattr(workflow_module, "_changes_any_code", lambda files: True)
    _a_sprint_with_advice_reviews(agents, monkeypatch)
    # Each specialist's line names its item: both are owed, so the sprint goes back to the lead once (SP.1).
    agents.scripts["advice_reviewer_together"] = [
        responds_with(AdviceReview(not_built=["UX-1: no rule below 600px", "DB-1: notes have no id"])),
        responds_with(AdviceReview()),
    ]
    agents.script("technical_lead", [responds_with(_milestone("testing"))] * 2)
    agents.script("specialist_testing", [responds_with(_specialist())] * 4)
    agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 2)
    agents.script("security_reviewer", [responds_with(_security_review())] * 2)
    caplog.set_level(logging.INFO, logger="app.graph.workflow")

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-one-call")

    assert state["stage"] == "complete", state.get("error")
    assert len(agents.requests["advice_reviewer_together"]) == 2  # the sprint, then its revision
    assert not agents.requests.get("advice_reviewer_ui_ux") and not agents.requests.get("advice_reviewer_database")
    asked = agents.last_request_text("advice_reviewer_together")
    assert "UI/UX specialist's advice" in asked and "database specialist's advice" in asked
    heard = agents.requests["milestone_reviewer"][0]["messages"][-1]["content"]
    assert "[UI/UX specialist] not built: UX-1: no rule below 600px" in heard
    assert "[database specialist] not built: DB-1: notes have no id" in heard
    assert sorted(state["advice_sent_back"]) == ["DB-1", "UX-1"]
