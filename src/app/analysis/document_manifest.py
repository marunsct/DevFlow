"""The documents this workflow produces, and nothing else.

`docs/` is the workflow's namespace. Every file in it is rendered by the
workflow from a stage's structured response, so a file an agent writes there
is at best ignored and at worst a second copy of a document the run acts on.

Measured across the 82 stored workspaces: nine document names appear in 55 to
82 of them, and about ninety more appear in exactly one - `placeholder.md`,
`empty.md`, `blocker.md`, `style.css.md`, `TaskCleanupReport.md`,
`old_architecture_review.md` beside `architecture_review_new.md`.

Counting calls rather than files, across the 50 stored transcripts:

    writes into docs/ of a document the workflow renders   229  (all refused)
    writes into docs/ of something else                    334  (all allowed)
    writes anywhere else in the project                  2,725

So one write in six went into `docs/`, and not one of them produced anything
any stage reads. 28 of the 50 runs created at least one; `implementation`
wrote 129 of them by itself.

This module is the single place the set is written down. `repository.py`
enforces it, the role prompts describe it and the audit reads it from here,
so the three cannot drift apart - which is how this codebase has broken the
same thing five times.

Deliberately about `docs/`, not about documentation. A product README, an API
guide or an architecture decision record that ships with the code are
legitimate deliverables and belong in the project directory beside the code
they describe, where the milestone reviewer reads them as part of the
product. Nothing here stops any of that.
"""

from __future__ import annotations

import difflib
from typing import NamedTuple


class Document(NamedTuple):
    """One document the workflow renders from a stage's structured response."""

    stem: str
    """File name without its extension."""

    stage: str
    """The stage whose structured response renders it."""

    summary: str
    """One line, for the prompt that tells agents what the set is."""


#: Every document this workflow produces, in the order a run produces them.
DOCUMENTS: tuple[Document, ...] = (
    Document("product_intake", "product_manager", "the approved brief"),
    Document("tools_and_models", "tools_models", "the technology comparison"),
    Document("technology_stack", "stack_selector", "the chosen stack"),
    Document("technical_specification", "principal_architect", "the specification"),
    Document("architecture_review", "architecture_review", "the architecture review"),
    Document("milestone_plan", "scrum_master", "the milestone plan"),
    Document("sprint_plan", "technical_lead", "the sprint plan"),
    Document("security_review", "security_review", "the security review"),
    Document("milestone_review", "milestone_review", "the milestone review"),
)

#: The stems, for a membership test.
RENDERED_STEMS: frozenset[str] = frozenset(document.stem for document in DOCUMENTS)

#: By stem, for a message that can name the owning stage.
BY_STEM: dict[str, Document] = {document.stem: document for document in DOCUMENTS}


#: Stems an agent reaches for when it mistakes "return your structured
#: response" for "write it down". Measured: `structured_response` 41 times as
#: `.md` and 8 as `.json`, plus `structured_output`, `summary_report` and
#: `final_output` once each.
_THE_ANSWER_ITSELF = ("structured_response", "structured_output", "final_output",
                      "final_response", "response", "output")


#: How alike two names must be before a reader would confuse them. Measured
#: against the names agents have actually written beside the workflow's own:
#: `tech_specification` scores 0.88 against `technical_specification`,
#: `tools_and_model` 0.97 against `tools_and_models`, while
#: `architecture_notes` (0.76) and `test_plan` (0.70) stay below.
CONFUSABLE = 0.8


def _stem_of(name: str) -> str:
    """The file name without its last extension, lowercased."""
    return name.rsplit(".", 1)[0].lower() if "." in name else name.lower()


def is_rendered(name: str) -> bool:
    """Whether `name` is one of the documents the workflow writes."""
    return _stem_of(name) in RENDERED_STEMS


def closest_rendered(name: str) -> tuple[float, Document] | None:
    """The rendered document this name is nearest to, if it is near one."""
    stem = _stem_of(name)
    if not stem:
        return None
    ratio, document = max(
        (difflib.SequenceMatcher(None, stem, other.stem).ratio(), other)
        for other in DOCUMENTS
    )
    return (ratio, document) if ratio >= CONFUSABLE else None


def why_it_does_not_belong(relative_parts: tuple[str, ...]) -> str:
    """Why this path may not be written, or "" if it may.

    Only paths under `docs/` are considered. A document deeper inside the
    project is the product's own and is none of this module's business.

    A nested path such as `docs/notes/README.md` is refused too, and for the
    same reason: the namespace is the directory, not its top level, and a
    subdirectory is the obvious thing to try next after a refusal.

    Three messages, because three different mistakes produce this path and a
    refusal that does not name the way out is the most expensive shape this
    harness has - two sprints have been lost to one.
    """
    if len(relative_parts) < 2 or relative_parts[0].lower() != "docs":
        return ""
    name = relative_parts[-1]
    stem = _stem_of(name)
    if not stem:
        return ""
    if stem in RENDERED_STEMS and len(relative_parts) == 2:
        return ""  # `_a_workflow_document` owns that refusal, with its own words.
    if len(relative_parts) > 2:
        return (
            f"Refusing to write '{'/'.join(relative_parts)}': 'docs/' holds only "
            "the documents this workflow renders from structured responses, and "
            "a subdirectory of it is still 'docs/'. " + describe() + " "
            "Documentation that ships with the product goes in the project "
            "directory beside the code it describes; a note for a later stage "
            "goes in your structured response."
        )

    if any(stem == marker or stem.startswith(marker) for marker in _THE_ANSWER_ITSELF):
        return (
            f"Refusing to write 'docs/{name}': your structured response reaches "
            "the workflow through what you return, not through a file. Nothing "
            "reads this path. Whatever you were about to put in it belongs in "
            "the fields of your response, and the run stops waiting for you as "
            "soon as you return them."
        )

    near = closest_rendered(name)
    if near is not None:
        _, document = near
        return (
            f"Refusing to write 'docs/{name}': it is a near-copy of the name "
            f"'docs/{document.stem}.md', which the workflow renders from the "
            f"'{document.stage}' stage's structured response. A reviewer with "
            "both in front of it reads the differences between them as "
            "contradictions in the design - that has ended a run before now. "
            f"Read 'docs/{document.stem}.md' if you need what it says. If you "
            "disagree with it, say so in your structured response, which the "
            "next stage actually receives."
        )

    return (
        f"Refusing to write 'docs/{name}': 'docs/' holds only the documents "
        "this workflow renders from structured responses, and nothing reads a "
        "file you add to it. " + describe() + " If this is a note for a later "
        "stage, put it in your structured response - `decisions` for something "
        "you settled, `risks` for something you are worried about, `blockers` "
        "for something that stops the work. If it is documentation that ships "
        "with the product, write it in the project directory beside the code "
        "it describes, where the reviewer reads it as part of the work."
    )


def not_rendered_yet(relative_path: str) -> str:
    """Why a workflow document is missing, or "" if the path is not one.

    The layout brief names every document in `docs/` and says to read them,
    but most exist only once the stage that renders them has run. One run's
    `technical_lead`, in the first sprint, read `docs/security_review.md` -
    which the security review renders at the end of a milestone - and was
    answered only "File does not exist within the repository".

    Only called for a path that is missing, so "has not run yet" is what the
    absence means: a document is rendered as its stage finishes.
    """
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part not in ("", ".")]
    if len(parts) != 2 or parts[0] != "docs" or not parts[1].lower().endswith(".md"):
        return ""
    document = BY_STEM.get(_stem_of(parts[1]))
    if document is None:
        return ""
    return (
        f" It is {document.summary}, which the workflow renders from the "
        f"'{document.stage}' stage's structured response, and that stage has not "
        "run yet in this run - there is nothing to read until it does. Work from "
        "the documents in `docs/` that exist now."
    )


def describe() -> str:
    """The set, as one sentence for a prompt. Rendered, never restated."""
    return (
        "The workflow renders exactly these, each from one stage: "
        + "; ".join(f"docs/{d.stem}.md ({d.summary}, from {d.stage})" for d in DOCUMENTS)
        + "."
    )


__all__ = [
    "BY_STEM",
    "CONFUSABLE",
    "DOCUMENTS",
    "Document",
    "RENDERED_STEMS",
    "closest_rendered",
    "describe",
    "is_rendered",
    "not_rendered_yet",
    "why_it_does_not_belong",
]
