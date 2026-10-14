"""A specification sent back to repair one section keeps the sections it dropped.

Asked to correct only `testing`, one run's architect returned `testing` alone -
two entries where there had been nine - and left `deployment` and
`acceptance_criteria` empty, though its previous answer had filled them.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from app.graph import workflow
from app.graph.workflow import _with_the_sections_it_dropped


class Spec(BaseModel):
    component_boundaries: list[str] = []
    api_and_event_contracts: list[str] = []
    data_flows: list[str] = []
    security_and_privacy: list[str] = []
    reliability_and_observability: list[str] = []
    testing: list[str] = []
    deployment: list[str] = []
    acceptance_criteria: list[str] = []
    summary: str = ""


def _full(**changes) -> Spec:
    sections = {name: [f"{name} as first written"] for name in Spec.model_fields if name != "summary"}
    return Spec(**{**sections, **changes})


def test_a_section_the_repair_left_empty_comes_from_the_answer_before() -> None:
    previous = _full()
    revised = Spec(testing=["corrected"], component_boundaries=["revised boundaries"])

    merged = _with_the_sections_it_dropped(revised, previous)

    assert merged.testing == ["corrected"]
    assert merged.component_boundaries == ["revised boundaries"]
    assert merged.deployment == ["deployment as first written"]
    assert merged.acceptance_criteria == ["acceptance_criteria as first written"]


def test_a_section_empty_in_both_stays_empty_for_the_missing_check() -> None:
    previous = _full(deployment=[])
    merged = _with_the_sections_it_dropped(Spec(testing=["t"]), previous)
    assert merged.deployment == []
    assert "deployment" in workflow._incomplete_specification_sections(merged)


def test_nothing_to_merge_with_returns_the_answer_unchanged() -> None:
    revised = Spec(testing=["t"])
    assert _with_the_sections_it_dropped(revised, None) is revised
    assert _with_the_sections_it_dropped(None, _full()) is None


def test_only_a_repair_merges_and_before_the_document_is_rendered() -> None:
    source = inspect.getsource(workflow)
    node = source[source.index("def principal_architect_node"):source.index("def architecture_review_node")]
    merge = node.index("_with_the_sections_it_dropped(")
    assert 'state.get("specification_repair_count", 0)' in node[merge - 200:merge]
    assert merge < node.index('"docs/technical_specification.md"')


def test_a_revision_after_review_sends_what_it_changes_and_keeps_the_rest() -> None:
    """One run's architect, sent back on a 60,000-character specification, read it
    out of its own saved conversation to write all of it again."""
    import re

    from app.agents.principal_architect import TechnicalSpecificationOutput, build_architecture_revision_request
    from test_graph_routing import _document, _repository

    previous = TechnicalSpecificationOutput(
        product_scope="Notes.", file_plan=["notes/src/app.ts - routes"], function_contracts=["createApp(): Hono"],
        library_usage=["hono - new Hono()"], testing=["node --test"],
    )
    revised = TechnicalSpecificationOutput(product_scope="Notes.", testing=["node --test, with a temp DATA_DIR"])

    merged = _with_the_sections_it_dropped(revised, previous)

    assert merged.testing == ["node --test, with a temp DATA_DIR"]
    assert merged.file_plan == ["notes/src/app.ts - routes"] and merged.library_usage == ["hono - new Hono()"]
    source = inspect.getsource(workflow)
    node = source[source.index("def principal_architect_node"):source.index("def architecture_review_node")]
    assert "or required_changes) and previous_specification is not None" in node
    request = build_architecture_revision_request(
        "{}", ["testing: name the data directory"], "intake", "tools", "stack",
        _repository("/r"), _document(),
    )["messages"][-1]["content"]
    rule = request[request.index("Send only the sections you change"):request.index("Address every item")]
    assert "kept exactly as it is in your previous" in rule
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", rule, re.I)
