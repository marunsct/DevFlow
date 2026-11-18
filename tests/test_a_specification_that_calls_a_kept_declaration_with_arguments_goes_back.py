"""A specification that calls a declaration the stack's setup keeps with no parameters, with arguments, goes back.

Measured on two Rust runs: the setup declares `pub fn app() -> Router` and its start file and tests call it bare; the
specification designed "main opens the Store ... calls axum::serve on app(store)". The builders followed the
specification, the setup's contract was raised against it every round, and two sprint attempts were spent.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.graph import workflow
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

CALLED_WITH_ARGUMENTS = (
    "- Startup: main opens the Store and wraps it in Arc.\n"
    "- Serving: main binds HOST:PORT with tokio::net::TcpListener and calls axum::serve on app(store).\n"
)
CALLED_AS_DECLARED = (
    "- notes-api/src/lib.rs: exposes pub fn app(), which opens the store from DATA_DIR itself.\n"
    "- Serving: main calls axum::serve on app() and nothing else.\n"
)


@pytest.fixture
def rust(monkeypatch):
    import app.stacks as stacks

    monkeypatch.setattr(stacks, "choose_pack", lambda stack, text: pack_named("rust-axum-api"))
    return {"stack_selection": SimpleNamespace(technology_stack=object()), "document": SimpleNamespace(text="")}


def test_a_call_with_arguments_is_a_major_finding(rust):
    finding = workflow._a_kept_signature_the_specification_calls_otherwise(rust, CALLED_WITH_ARGUMENTS)

    assert finding is not None and finding.severity == "major"
    assert "app(store)" in finding.description and "pub fn app() -> Router" in finding.description
    assert not BANNED.search(finding.description + finding.required_remediation)


def test_a_call_as_declared_is_none(rust):
    assert workflow._a_kept_signature_the_specification_calls_otherwise(rust, CALLED_AS_DECLARED) is None


def test_it_is_raised_once_and_asked_again_by_the_revision_check(rust):
    assert workflow._a_kept_signature_the_specification_calls_otherwise(
        {**rust, "specification_signatures_checked": True}, CALLED_WITH_ARGUMENTS) is None
    assert len(workflow._the_harness_findings_still_open(
        {**rust, "specification_signatures_checked": True}, CALLED_WITH_ARGUMENTS, ["signature"])) == 1
    assert "specification_signatures_checked" in workflow.WorkflowGraphState.__annotations__
