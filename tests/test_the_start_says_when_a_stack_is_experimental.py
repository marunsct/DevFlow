"""The start says when the stack a brief asks for, or the model's tier, is experimental here.

Deep review 2026-11-18, item F1: a customer install has no operator auditing every run, and nothing told the owner
before a run started that the stack the brief named had too few scored runs to say how reliably it delivers.
"""
from __future__ import annotations

from app.stacks import support_matrix

GO_BRIEF = """# Notes service

## Features
- Add a note
- Go to the list of notes and delete one

## Technical constraints
- Written in Go with the standard library
"""

PYTHON_BRIEF = GO_BRIEF.replace("Written in Go with the standard library", "Python, with FastAPI")


def test_a_brief_asking_for_go_is_told_it_is_experimental():
    said = support_matrix.for_the_brief(GO_BRIEF)

    assert said is not None and said["status"] == "experimental" and said["languages"] == ["go"]


def test_a_brief_asking_for_python_is_not_warned_and_a_feature_s_words_are_not_a_stack():
    assert support_matrix.for_the_brief(PYTHON_BRIEF) is None
    assert support_matrix.for_the_brief("# Notes\n\n## Features\n- Go to the list\n- Add a note\n") is None


def test_a_model_measured_weak_is_experimental_on_every_stack():
    said = support_matrix.for_the_brief(PYTHON_BRIEF, tier="weak")

    assert said is not None and said["status"] == "experimental"


def test_the_matrix_supports_measured_python_and_javascript_services_and_not_the_rest():
    rows = {row["pack"]: row for row in support_matrix.matrix()}

    assert (rows["python-http-api"]["standard"], rows["python-http-api"]["weak"]) == ("supported", "experimental")
    assert rows["node-http-api"]["strong"] == "supported"
    assert rows["rust-axum-api"]["standard"] == "experimental" and rows["go-gin-api"]["standard"] == "experimental"
    assert rows["go-gin-api"]["evidence"] == "no scored runs yet"


def test_the_preview_carries_the_warning_and_the_server_serves_the_matrix(client):
    preview = client.post("/api/runs/preview", json={"brief": GO_BRIEF}).json()
    table = client.get("/api/support-matrix").json()

    assert preview["stack_support"]["status"] == "experimental" and "go" in preview["stack_support"]["languages"]
    assert {"pack": "python-http-api", "standard": "supported"}.items() <= next(
        row for row in table["rows"] if row["pack"] == "python-http-api").items()
