"""A run that builds from a specification still calling the setup's declaration with arguments is told which stands.

Measured on one Rust run: the review raised that the specification calls `app` with arguments, the architect's revision
fixed one sentence and kept `pub fn app(state: AppState) -> Router` in another, the run built from that specification
anyway, and the model's rulings on the open findings did not take it up - the builders were left to follow the
specification against the setup. The setup's declaration is ruled to stand, with no model asked.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.agents import specification_rulings
from app.graph import workflow
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPECIFICATION = (
    "- Database Initialization Flow: On startup, app() reads the resolved database path from configuration.\n"
    "- notes-api/src/lib.rs: Exports pub fn app(state: AppState) -> Router that registers all routes.\n"
)


@pytest.fixture
def rust(monkeypatch, tmp_path):
    import app.stacks as stacks

    monkeypatch.setattr(stacks, "choose_pack", lambda stack, text: pack_named("rust-axum-api"))
    return {"stack_selection": SimpleNamespace(technology_stack=object()), "document": SimpleNamespace(text=""),
            "repository": SimpleNamespace(root_path=str(tmp_path)), "technical_specification": SPECIFICATION}


def test_each_sentence_calling_it_otherwise_is_found(rust):
    found = workflow.kept_signatures_called_otherwise(rust, SPECIFICATION)

    assert [(relative, written) for relative, written, _ in found] == [("src/lib.rs", "pub fn app() -> Router")]
    assert "app(state: AppState)" in found[0][2]


def test_the_setup_s_declaration_is_ruled_to_stand_and_shown_to_the_builders(rust):
    update: dict = {}
    added = specification_rulings.the_setup_s_declarations_stand(
        rust, update, workflow.kept_signatures_called_otherwise(rust, SPECIFICATION))

    assert len(added) == 1 and "pub fn app() -> Router" in added[0]["stands"]
    section = specification_rulings.the_rulings_section(rust["repository"].root_path)
    assert "pub fn app() -> Router" in section and "app(state: AppState)" in section
    assert not BANNED.search(section)
    # Asked again, nothing is added twice.
    assert specification_rulings.the_setup_s_declarations_stand(
        rust, update, workflow.kept_signatures_called_otherwise(rust, SPECIFICATION)) == []


def test_the_design_escalation_records_it(rust, monkeypatch):
    from app.graph import escalation

    monkeypatch.setattr(specification_rulings, "settle", lambda *a, **k: [])
    escalation._build_from_the_latest_specification(
        rust, {}, "The architecture review still asks for changes.", decided_by="auto", next_stage="next", model=None)

    assert "pub fn app() -> Router" in specification_rulings.the_rulings_section(rust["repository"].root_path)
