"""`docs/` holds nine documents, and the harness no longer says otherwise.

Measured across the 82 stored workspaces: nine names appear in 55 to 82 of
them and about ninety more appear in exactly one - `placeholder.md`,
`empty.md`, `blocker.md`, `style.css.md`, `TaskCleanupReport.md`,
`old_architecture_review.md` beside `architecture_review_new.md`. Counting
calls across the 50 stored transcripts: 563 writes went into `docs/`, 229
refused and 334 allowed, in 28 of 50 runs, and not one produced something a
later stage read.

The half of this that matters most is the prompt. Four role prompts said, in
capitals, "All documentation goes in the `docs/` directory", and
`_WRITING_RULES` told every specialist to put its reports there. Enforcing a
manifest without changing those would have been the same mistake as the
Playwright `webServer` (§4ao): the harness ordering a file into existence and
then refusing the sprint for it.
"""

from __future__ import annotations

import inspect

import pytest

from app.analysis.document_manifest import (
    DOCUMENTS,
    RENDERED_STEMS,
    closest_rendered,
    describe,
    is_rendered,
    why_it_does_not_belong,
)


def test_the_nine_are_the_nine():
    assert len(DOCUMENTS) == 9
    assert len(RENDERED_STEMS) == 9


def test_the_tool_and_the_manifest_cannot_disagree():
    """One list. Two copies is how this codebase has broken things five times."""
    from app.tools.repository import WORKFLOW_DOCUMENTS

    assert WORKFLOW_DOCUMENTS == frozenset(f"{stem}.md" for stem in RENDERED_STEMS)


def test_every_document_names_a_stage_that_exists():
    """A manifest that names a stage nothing runs is a manifest nobody checked."""
    from app.graph import workflow

    source = inspect.getsource(workflow)
    for document in DOCUMENTS:
        assert document.stage in source, f"{document.stem} names an unknown stage"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda d: d.stem)
def test_a_rendered_document_is_not_refused_by_the_manifest(document):
    """`_a_workflow_document` owns that refusal, and says something better."""
    assert why_it_does_not_belong(("docs", f"{document.stem}.md")) == ""


@pytest.mark.parametrize(
    "name, expected",
    [
        ("structured_response.md", "through what you return"),
        ("structured_response.json", "through what you return"),
        ("final_output.md", "through what you return"),
        ("tech_specification.md", "near-copy"),
        ("tools_and_model.md", "near-copy"),
        ("README.md", "nothing reads a file you add to it"),
        ("QA_report.md", "nothing reads a file you add to it"),
        ("placeholder.md", "nothing reads a file you add to it"),
        ("style.css.md", "nothing reads a file you add to it"),
    ],
)
def test_each_mistake_gets_the_message_that_fits_it(name: str, expected: str):
    message = why_it_does_not_belong(("docs", name))

    assert expected in message
    # Every one of them, without exception: a refusal that names no way out is
    # the most expensive shape this harness has.
    assert "structured response" in message or "project directory" in message


def test_a_subdirectory_of_docs_is_still_docs():
    assert why_it_does_not_belong(("docs", "notes", "README.md")) != ""
    assert why_it_does_not_belong(("docs", "sub", "product_intake.md")) != ""


def test_a_document_inside_the_project_is_none_of_its_business():
    assert why_it_does_not_belong(("task-manager", "README.md")) == ""
    assert why_it_does_not_belong(("src", "docs", "notes.md")) == ""
    assert why_it_does_not_belong(("README.md",)) == ""


def test_the_directory_is_matched_whatever_its_case():
    assert why_it_does_not_belong(("DOCS", "README.md")) != ""


def test_a_name_far_from_all_nine_is_not_called_a_near_copy():
    assert closest_rendered("api_reference.md") is None
    assert closest_rendered("QA_report.md") is None


def test_is_rendered_ignores_the_extension():
    assert is_rendered("product_intake.md")
    assert is_rendered("product_intake.txt")
    assert not is_rendered("product_intakes.md")


def test_the_description_names_every_document_and_its_stage():
    described = describe()
    for document in DOCUMENTS:
        assert document.stem in described
        assert document.stage in described
