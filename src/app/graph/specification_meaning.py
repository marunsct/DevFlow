"""Statements of a first draft that contradict each other in different words, found by one call (plan PA.7, the rest).

The consistency pass (`specification_consistency`) compares what sections repeat - a route's status codes, a file's
name, a limit, an advice decision - and finds a disagreement only where the two lines share the value they disagree
on. Measured over the stored architecture reviews: a blocking finding on one small run was `data_flows` "If the file
contains malformed JSON, it logs an error and exits" against `reliability_and_observability` "corrupted files result
in starting with an empty store rather than crashing" - one behaviour, said two ways, no shared word for the
mechanical pass to match; others were a data layer that "reads the file on each call" against "loaded once at
startup and kept in memory", and a directory the service "refuses to start" without against one it "creates if it
does not exist". Each came back from the review as blocking or major and cost the design a second pass.

So before the first review, one call is shown the draft's statements numbered and names the pairs that cannot both
be true (`contradictions`); each becomes a disagreement of kind "meaning" beside the mechanical ones, and the same
settle call rewrites only those lines (`specification_consistency.settled`). A pair the mechanical pass already
holds is not raised twice. A draft shorter than `FEWEST_CHARACTERS` is read whole by its reviewer and is not sent; a
call that fails or answers nothing usable finds nothing. Always on: a quality fix, one call a design.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: A draft whose statements are shorter than this is not sent: its reviewer reads it whole.
FEWEST_CHARACTERS = 8_000
#: The statements shown at most, in characters; the rest of a longer draft is left out.
MOST_CHARACTERS = 60_000
#: Characters of one statement shown.
STATEMENT_LIMIT = 500
#: Contradictions taken at most from one answer.
MOST_FOUND = 10


def statements(specification: Any) -> list[tuple[str, str]]:
    """The draft's statements as (section, line), in section order, within `MOST_CHARACTERS`."""
    from app.graph.specification_consistency import _sections

    shown: list[tuple[str, str]] = []
    total = 0
    for section, lines in _sections(specification).items():
        for line in lines:
            total += min(len(line), STATEMENT_LIMIT) + len(section) + 8
            if total > MOST_CHARACTERS:
                return shown
            shown.append((section, line))
    return shown


def find_request(numbered: list[tuple[str, str]], context: str = "") -> str:
    """What the one call is asked: the statements numbered, and how to answer."""
    listed = "\n".join(f"[{number}] `{section}`: {line[:STATEMENT_LIMIT]}"
                       for number, (section, line) in enumerate(numbered, start=1))
    return "\n\n".join(part for part in (
        "These are the statements of a software product's technical specification, numbered, each with the section "
        "it is in. The sections were written in separate parts. Find the pairs of statements that cannot both be true "
        "of the product built from it: two statements about the same behaviour, value or file that say different "
        "things, even in different words - one says a malformed data file stops the service and another that the "
        "service then starts empty; one says data is read from disk on each request and another that it is loaded "
        "once and kept in memory. A statement that adds detail to another, or one about a different part of the "
        "product, is not a contradiction. Name only pairs you are sure of.",
        (context or "").strip()[:8_000],
        "--- The statements ---\n" + listed,
        'Reply with one JSON object and nothing else: {"contradictions": [{"statements": [<number>, <number>], '
        '"about": "<what they disagree about, in a few words>"}]} - {"contradictions": []} when there are none.',
    ) if part)


def _pairs(reply: Any) -> list[tuple[list[int], str]]:
    from app.graph.specification_parts import _the_object_in

    found = _the_object_in(reply) or {}
    pairs = []
    for item in found.get("contradictions") or []:
        if not isinstance(item, dict):
            continue
        numbers = [n for n in item.get("statements") or item.get("lines") or [] if isinstance(n, int)]
        if len(numbers) >= 2:
            pairs.append((numbers, " ".join(str(item.get("about") or "").split())))
    return pairs


def contradictions(specification: Any, model: Any, context: str = "", known: Any = ()) -> list[Any]:
    """The statement pairs one call names as contradicting each other, as disagreements of kind "meaning"; [] when the
    draft is short, there is no model, or the call fails. Pairs whose lines `known` (the mechanical disagreements)
    already hold are left out. Never raises."""
    from app.graph.specification_consistency import Disagreement

    try:
        numbered = statements(specification)
        if model is None or sum(len(line) for _, line in numbered) < FEWEST_CHARACTERS:
            return []
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.agents.thinking import without_reasoning
        from app.observability.direct_calls import config_for_this_run

        reply = without_reasoning(model).invoke([
            SystemMessage(content="You find the statements of a software technical specification that contradict "
                                  "each other."),
            HumanMessage(content=find_request(numbered, context)),
        ], **config_for_this_run("principal_architect"))
        held = {(section, " ".join(line.split())) for entry in known or () for section, line in entry.lines}
        found: list[Any] = []
        for numbers, about in _pairs(reply):
            lines = [numbered[n - 1] for n in dict.fromkeys(numbers) if 0 < n <= len(numbered)]
            if len(lines) < 2 or all((section, " ".join(line.split())) in held for section, line in lines):
                continue
            found.append(Disagreement(
                "meaning", about[:80] or "one behaviour",
                f"these statements cannot both be true{': ' + about if about else ''}", lines,
            ))
        logger.info("Specification consistency pass: %d contradiction(s) in meaning", len(found))
        return found[:MOST_FOUND]
    except Exception as error:  # noqa: BLE001 - nothing found is the draft as it was
        logger.info("Specification consistency pass: the contradictions could not be found: %s", str(error)[:200])
        return []


__all__ = ["FEWEST_CHARACTERS", "MOST_CHARACTERS", "contradictions", "find_request", "statements"]
