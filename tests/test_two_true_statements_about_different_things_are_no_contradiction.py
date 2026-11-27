"""Two true statements about different things are not "opposite things" in the specification (LF.1633).

Measured over the 147 design escalations of 143 stored runs: the contradiction check (`one_design_review`, by
`design_revision_cross_checked.opposite_statements`) named 989 pairs, and none of the hundreds read in full was a
contradiction that mattered: "returns 204 with no response body" against "the response body is an array", "if N is not
a positive integer" against "validates it is a positive integer", "without I/O side effects" against "without side
effects", a decision's rejected alternative against the decision. 118 escalations had only such points open, the
release listed them as gaps, and the escalation's rulings on them were read by every later stage. The statements below
are captured from those specifications; a denial of something of the whole product is still caught.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.graph import design_revision_cross_checked as cross
from app.graph import one_design_review


class _Spec(BaseModel):
    product_scope: str = ""
    component_boundaries: list[str] = []
    api_and_event_contracts: list[str] = []
    data_flows: list[str] = []
    security_and_privacy: list[str] = []
    reliability_and_observability: list[str] = []
    testing: list[str] = []
    acceptance_criteria: list[str] = []
    interface_design: list[str] = []
    domain_model: list[str] = []
    test_cases: list[str] = []
    decisions: list[dict] = []


# Captured pairs of true statements about different things: a case of one route, a condition, the same denial in other
# words, a test's step.
DIFFERENT_THINGS = [
    ("response body",
     "DELETE /notes/{id} accepts an integer path parameter; returns 204 with no response body on success, or 404 with a "
     "JSON error body if not found.",
     "AC-2 List all notes (populated): Create two notes via POST /notes. Send GET /notes. Assert response status is 200. "
     "Assert response body is a 2-element array containing both notes with correct id, title, and body fields, sorted "
     "by id ascending."),
    ("response body",
     "DELETE /notes/{id} (204): No response body.",
     "AC-7: In every test that returns a note (POST, GET /notes/{id}, PUT /notes/{id}), assert the response body is "
     "valid JSON with exactly three fields: id (integer), title (string), and body (string)."),
    ("positive integer",
     "UX-3: The --top flag is parsed as a string and validated at parse time. If N is not a positive integer, it prints "
     "'Error: --top requires a positive integer' to stderr and exits with status 2.",
     "Argument parsing flow: parse_args() in cli.py receives argv, sets --top as type=str, and manually validates it is "
     "a positive integer. If validation fails, it prints 'Error: --top requires a positive integer' to stderr and exits "
     "with code 2 before any file I/O."),
    ("side effects",
     "`wordstats.analyzer`: Pure logic module. Exports `count_words_lines_characters(text: str) -> dict` and "
     "`get_top_frequent_words(text: str, n: int) -> list[dict]`. No I/O dependencies. Importable by tests without side "
     "effects.",
     "Unit tests import wordstats.analyzer directly to test pure logic functions count_words_lines_characters and "
     "get_top_frequent_words without I/O side effects."),
    ("trailing newline",
     "Counts: A triple of integers — words (number of word tokens), lines (number of lines, last line counted even "
     "without trailing newline), characters (total byte count including newlines).",
     "AC-6: Line counting includes the last line even if it lacks a trailing newline."),
    ("authorization header",
     "AC-3 POST/GET/PATCH/DELETE /items without Authorization header -> 401 Unauthorized {\"error\": \"Authentication "
     "required\"} (Validates auth enforcement on all item endpoints)",
     "tasks-api/tasks_api/routes/items.py — Items blueprint module. Each route handler requires valid Bearer token from "
     "Authorization header (401 if missing/invalid), scopes all queries to the authenticated user's account_id."),
    ("note exists",
     "GET /notes/{id}: No note exists with the specified integer ID. Returns 404 with {\"error\": \"Note not found\"}. "
     "No data is accessed.",
     "GET /notes/<int:id>: Returns 200 with the note {\"id\": <integer>, \"title\": <string>, \"body\": <string>} if "
     "the note exists."),
    ("rate limiting",
     "Deferred: authentication, search, filtering, sorting, pagination on listing, rate limiting, request logging, "
     "metrics, graceful shutdown signal handling.",
     "Rate limiting is not provided; the brief defers it. Repeated signin attempts are not throttled, so the bcrypt cost "
     "is the only brake on password guessing."),
    ("request body",
     "Logging: tracing-subscriber writes to stdout with the filter from RUST_LOG, defaulting to info. Each request logs "
     "only method, path and response status. No request body and no note content is logged.",
     "POST /notes — Request body: JSON object with 'title' (string, required, non-empty) and 'body' (string, required)."),
    ("empty string",
     "title: String. Required. Must not be null, empty string, or whitespace-only after trimming. Validated on creation "
     "and update.",
     "body: String. Optional. May be null or omitted in JSON input. If provided, must be a string (empty string is "
     "acceptable). Stored as-is."),
    ("business logic",
     "Program.cs — ASP.NET Core application entry point. Builds the web host and maps all HTTP routes. No business logic "
     "lives here.",
     "Service Layer: NoteService handles business logic including validation (title presence/non-emptiness) and "
     "transaction wrapping."),
]


def test_true_statements_about_different_things_are_not_paired():
    for subject, one, other in DIFFERENT_THINGS:
        assert cross.opposite_statements({"a": [one]}, {"b": [other]}) == [], subject
        assert cross.opposite_statements({"b": [other]}, {"a": [one]}) == [], subject


def test_a_decision_s_rejected_alternative_is_not_what_the_specification_says():
    """Measured: "No graceful shutdown (immediate exit)" among a decision's alternatives was named against the
    component that does what the decision chose."""
    specification = _Spec(
        component_boundaries=[
            "main.go — Application bootstrap. Reads PORT (default 8080) and DATA_DIR environment variables, creates "
            "DATA_DIR if missing, registers signal handler for SIGTERM/SIGINT for graceful shutdown, and calls "
            "server.ListenAndServe."],
        decisions=[{
            "title": "Graceful shutdown on SIGTERM/SIGINT",
            "context": "The reliability specialist recommends graceful shutdown for production readiness.",
            "alternatives": ["No graceful shutdown (immediate exit)", "Shutdown only on SIGKILL"],
            "decision": "Register os/signal handler for SIGTERM and SIGINT, stop accepting new requests via "
                        "server.Shutdown(ctx) with bounded context timeout",
            "rationale": "Allows in-flight requests to finish.",
        }],
    )

    assert one_design_review.contradictions(specification) == []


def test_a_denial_of_something_of_the_whole_product_is_still_caught():
    specification = _Spec(
        product_scope=("An HTTP API that stores short notes for other programs. It does not implement authentication, "
                       "search, filtering, tags, categories, metadata, rate limiting, access controls, or API "
                       "versioning."),
        api_and_event_contracts=[
            "Rate limiting: 5 requests per minute per IP on /auth/login, /auth/register, and /auth/refresh. Returns 429 "
            "with {\"error_code\": \"RATE_LIMITED\"} when exceeded."],
        reliability_and_observability=["No graceful shutdown: the process exits at once."],
        data_flows=["Graceful shutdown is supported on SIGTERM."],
    )

    found = one_design_review.contradictions(specification)

    assert len(found) == 2
    assert any('"rate limiting"' in point and "`product_scope`" in point and "`api_and_event_contracts`" in point
               for point in found)
    assert any('"graceful shutdown"' in point for point in found)


def test_a_denial_said_of_one_route_is_opposite_to_a_statement_about_that_route():
    pairs = cross.opposite_statements(
        {"api_and_event_contracts": ["DELETE /notes/{id} (204): No response body."]},
        {"test_cases": ["DELETE /notes/{id}: assert 200 and the response body is the deleted note."]},
    )

    assert [pair[0] for pair in pairs] == ["response body"]
