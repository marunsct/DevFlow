"""The specification's part writers are given the specialists' advice numbered with its ids (harness review HR2.D.1).

They were given it as raw JSON with no ids while the check that follows demands one decision line per id: 224 rounds
over 120 runs asked again for decisions on ids the writer was never shown.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.specialist_advice import advice_block

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_parts_context_carries_the_numbered_advice(tmp_path, monkeypatch) -> None:
    from app.agents.product_manager import ProductManagerOutput
    from workflow_node_stubs import run_node

    told = []
    advice = {"database": ["Index the owner column"], "backend": ["Validate the body"]}

    def with_the_parts_written(specification, model, context):
        told.append(context)
        return specification

    run_node(monkeypatch, tmp_path, "principal_architect", answer=None, two_models=True,
             product_intake=ProductManagerOutput(product_name="Notes"), tools_models={"plan": "local"},
             document=SimpleNamespace(text="Notes."), specialist_advice=advice,
             overrides={"app.agents.research_brief.research_notes": lambda *a, **k: "",
                        "app.graph.workflow._fast_delivery": lambda: True,
                        "app.graph.specification_parts.with_the_parts_written": with_the_parts_written})

    (context,) = told
    assert advice_block(advice) in context
    assert "--- Specialists' advice ---" not in context and '"database"' not in context, "not the raw form any more"


def test_the_numbered_advice_names_every_id_and_the_rule() -> None:
    block = advice_block({"database": ["Index the owner column"], "backend": ["Validate the body", "Return 404 on a miss"]})
    for ident in ("DB-1", "BE-1", "BE-2"):
        assert f"- {ident}:" in block
    assert "specialist_advice_decisions" in block
    assert not BANNED.search(block)
