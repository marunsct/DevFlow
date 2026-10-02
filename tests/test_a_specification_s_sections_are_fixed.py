"""Both sides of the architecture review are told the specification's sections.

Measured on one run. The reviewer required a "ui_design" section, then
"code_size_governance", "testing_infrastructure" and "deployment_artifacts".
The specification is a schema: the architect cannot add a field, wrote what it
could into the sections that exist, and the reviewer found the named sections
still missing. Six revisions of the same four findings, and the run ended
without a line of code.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.architecture_reviewer import build_architecture_review_request
from app.agents.principal_architect import (
    TechnicalSpecificationOutput,
    build_architecture_revision_request,
    the_sections_a_specification_has,
)


def _document():
    return SimpleNamespace(text="# Brief\n\nBuild a thing.\n", source_type="markdown", truncated=False)


def test_every_section_of_the_schema_is_named() -> None:
    note = the_sections_a_specification_has(reader="reviewing")

    for name in TechnicalSpecificationOutput.model_fields:
        assert f"`{name}`" in note


def test_the_reviewer_is_told_not_to_require_a_new_one(tmp_path) -> None:
    body = build_architecture_review_request("the specification", str(tmp_path))["messages"][0]["content"]

    assert "no revision can add one" in body
    assert "do not require a new section by name" in body
    assert body.index("the specification") < body.index("no revision can add one")


def test_the_architect_is_told_where_such_a_change_goes() -> None:
    body = build_architecture_revision_request(
        "previous spec", ['Add a "ui_design" section.'], "intake", "tools", "stack",
        SimpleNamespace(branch="main", commit="abc123", root_path="/tmp"), _document(),
    )["messages"][0]["content"]

    assert "no revision can add one" in body
    assert "in the existing section it belongs to" in body
    assert body.index("Required changes") < body.index("no revision can add one")
