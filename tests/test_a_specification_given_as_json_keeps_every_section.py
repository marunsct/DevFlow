"""A specification that reaches a request as JSON keeps every section in part, not just its head.

Measured on a medium run: the architecture review was given the specification as its JSON - no headings - so the
budget cut it to its head, at `function_contracts`. The error catalogue and every section after it were never shown,
and on each of nine reviews the reviewer raised that a section the specification had did not exist.
"""

from __future__ import annotations

import json

from app.agents.text_budget import excerpt

#: The specification's keys in the order its JSON gives them, as captured from that run.
_KEYS = (
    "product_scope", "component_boundaries", "domain_model", "api_and_event_contracts", "data_flows",
    "security_and_privacy", "reliability_and_observability", "testing", "deployment", "open_questions",
    "acceptance_criteria", "interface_design", "interface_contract", "specialist_advice_decisions", "file_plan",
    "function_contracts", "data_contracts", "error_catalogue", "implementation_order", "test_cases",
    "configuration", "library_usage", "decisions",
)


def _specification() -> str:
    spec = {key: [f"{key} entry {n}: " + "detail " * 30 for n in range(40 if key == "function_contracts" else 6)]
            for key in _KEYS}
    spec["error_catalogue"] = ["DUPLICATE_EMAIL (409): the email is registered already"]
    spec["decisions"] = [{"title": "ADR-08 Password hashing", "decision": "bcrypt directly"}]
    return json.dumps(spec, indent=2)


def test_every_key_of_a_json_specification_survives_the_trim() -> None:
    text = _specification()
    budget = len(text) // 3

    fitted = excerpt(text, budget, what="technical specification")

    assert all(f'"{key}":' in fitted for key in _KEYS)
    assert "DUPLICATE_EMAIL (409)" in fitted and "ADR-08 Password hashing" in fitted
    assert "every section is here" in fitted and "of `function_contracts` not shown" in fitted
    assert len(fitted) <= budget


def test_the_architecture_review_is_shown_the_sections_after_the_cut() -> None:
    from app.agents.architecture_reviewer import build_architecture_review_request

    text = _specification()
    import os
    os.environ["CTX_SPECIFICATION_BUDGET"] = str(len(text) // 3)
    try:
        request = build_architecture_review_request(text, "/workspace")["messages"][0]["content"]
    finally:
        del os.environ["CTX_SPECIFICATION_BUDGET"]

    assert '"error_catalogue":' in request and '"decisions":' in request


def test_json_that_is_not_an_object_is_still_cut_to_its_head() -> None:
    text = json.dumps(["x" * 50] * 100)
    assert excerpt(text, 300, what="notes").startswith(text[:300] + "\n\n[Excerpt:")
