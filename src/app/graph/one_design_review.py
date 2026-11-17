"""The design is reviewed once and revised once; what is still open after that is settled, not reviewed again (LR.42
D3, behind `ONE_DESIGN_REVIEW`).

Measured before it (docs/measuring.md, D1+D2 and D3): every run of two families escalated at the second design review,
and the second review raised findings the first had not - a whole review and revision for each, on a document the
acceptance suite, written from the brief, goes on to judge anyway. The design escalation already builds from the latest
specification and records what is open as known risks (`app.graph.escalation`), and with `SETTLE_SPEC_CONTRADICTIONS`
settles the contradictions among them in one call.

So after the first review and one revision the reviewer is not asked again. Two deterministic gates decide instead:

1. the workflow's own design checks, asked again of the revised specification (`_THE_HARNESS_S_DESIGN_CHECKS`);
2. statements of the whole specification that say opposite things about one subject (`contradictions`, by the
   matching of `design_revision_cross_checked.opposite_statements`, no model call).

Nothing open: the specification is approved. Anything open goes to the design escalation as its findings, so it is
recorded as a known risk, or settled there. An efficiency change with a quality risk - a second review can catch an
error the revision brings in - so a switch, measured on hidden scores and design minutes.
"""
from __future__ import annotations

from typing import Any

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its decision gives, written to the run's decision record, which the audit's switch-firing check reads.
SAID = "revised once and not reviewed again"

#: Contradictions carried to the escalation: each is a known risk, and a long list says nothing a short one does not.
MOST_CONTRADICTIONS = 12
#: Characters of one statement quoted in an open point.
STATEMENT_LIMIT = 400
#: Sections that state no fact about the product: questions asked, and advice taken or turned down.
NOT_STATEMENTS = frozenset({"open_questions", "specialist_advice_decisions"})


def enabled() -> bool:
    return is_on("ONE_DESIGN_REVIEW", ON_BY_DEFAULT)


def applies(revisions: int) -> bool:
    """Whether this review is the second: on, and the specification has been revised once since the first."""
    try:
        return enabled() and int(revisions or 0) >= 1
    except (TypeError, ValueError):
        return False


def contradictions(specification: Any) -> list[str]:
    """Each pair of statements of the specification that say opposite things about one subject, as an open point.

    Every section is checked against every other, both ways; a pair is named once. Never raises.
    """
    try:
        from app.graph.design_revision_cross_checked import _dumped, denies, opposite_statements, statements

        if specification is None:
            return []
        sections = {name: statements(value) for name, value in _dumped(specification).items()
                    if name not in NOT_STATEMENTS}
        sections = {name: said for name, said in sections.items() if said}
        found: list[str] = []
        seen: set[frozenset[tuple[str, str]]] = set()
        seen_denials: set[tuple[str, str]] = set()
        for name, said in sections.items():
            others = {other: theirs for other, theirs in sections.items() if other != name}
            for subject, section, statement, other, their in opposite_statements({name: said}, others):
                key = frozenset({(section, statement), (other, their)})
                # One denial is one point, however many statements mention its subject. Measured over four runs: 7
                # denials ("DELETE ... 204 with no response body") were named 43 times, once against each endpoint
                # that has a body, and filled the cap.
                denial = (subject, statement if denies(statement, subject) else their)
                if key in seen or denial in seen_denials:
                    continue
                seen.add(key)
                seen_denials.add(denial)
                found.append(
                    f"The specification says opposite things on \"{subject}\": `{section}` says: "
                    f"{statement[:STATEMENT_LIMIT]} - while `{other}` says: {their[:STATEMENT_LIMIT]}"
                )
                if len(found) >= MOST_CONTRADICTIONS:
                    return found
        return found
    except Exception:  # noqa: BLE001 - a gate that cannot read the document finds nothing, as without it
        return []


__all__ = ["MOST_CONTRADICTIONS", "NOT_STATEMENTS", "ON_BY_DEFAULT", "SAID", "applies", "contradictions", "enabled"]
