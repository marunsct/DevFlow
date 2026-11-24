"""A group of values compared in a normal form is reported in that form (LF.1317).

Measured on two runs of one brief ("Words are compared in lower case"): the products counted case-insensitively and
printed each word as first read ("The 3"); the hidden tests expecting "the 3" failed (2 of 8 each) while the runs' own
locked suites passed. The architect's comparison rule (LF.780) and the suite writer's (LF.1255) did not reach the code
that groups the values: the builders were never told which spelling a group is reported in.

`A_GROUP_IN_ITS_NORMAL_FORM` is one sentence, said where the interface is designed (the principal architect) and where
the grouping is written (the builders of product code, and each product file's draft). The acceptance suite's matching
rule is `app.acceptance.requests.TESTS_ASSUME_ONLY_WHAT_THEY_MADE`.
"""

from __future__ import annotations

A_GROUP_IN_ITS_NORMAL_FORM = (
    "Where the product groups or counts values that are compared in a normal form - in lower case, trimmed, accents "
    "folded - it reports each group in that normal form, never in the spelling it read first: a group has no single "
    "original spelling. Only where the brief says which spelling to show is that one shown."
)


def for_a_draft(path: str) -> str:
    """The sentence for a product file's draft; "" for a test, a document or a configuration file."""
    from app.analysis.file_kinds import classify_file

    return A_GROUP_IN_ITS_NORMAL_FORM if classify_file(path) == "application" else ""


__all__ = ["A_GROUP_IN_ITS_NORMAL_FORM", "for_a_draft"]
