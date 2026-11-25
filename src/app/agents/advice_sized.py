"""Specialist advice sized to the brief (plan PA.9, behind `ADVICE_SIZED_TO_THE_BRIEF`).

Measured over 11 small runs: 38 consultations returned 359 items, 9.4 of the 10 allowed each - the cap was the
target. Every item has to be adopted or declined by the architect and then checked by an advice reviewer each sprint;
one medium specification held 88 advice decisions, and a rate limit no suite could run under was adopted advice.

With the switch on:
- the cap follows the brief's acceptance criteria: `MOST_FOR_A_SMALL_BRIEF` items up to `SMALL_BRIEF` criteria,
  `MOST_FOR_A_MEDIUM_BRIEF` up to `MEDIUM_BRIEF`, the full ten beyond. The testing specialist's items are one per
  criterion by design, so its cap is unchanged;
- each item opens with whether the brief asks for it: `[asked] "<the brief's words>"` or `[beyond]`; the items the
  brief asks for are kept first when an answer is cut to the cap;
- the architect is told an item beyond the brief is declined unless its decision line quotes the brief line that
  needs it, and the harness declines one adopted without such a quote (`with_items_beyond_the_brief_declined`).

Off in code until measured, two runs a family: it changes the advice, and so the specification.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file and each run's own setting decide.
ON_BY_DEFAULT = False

#: What the admin page says this switch does.
explanation = ("Each specialist adviser gives at most 3 items for a brief of up to 10 acceptance criteria and 5 up to "
               "20, each marked as asked for by the brief or beyond it; the architect declines an item beyond the "
               "brief unless it quotes the brief line that needs it.")

#: The words every request it changes carries, which the audit's switch-firing check reads.
SAID = "Advice sized to the brief"

SMALL_BRIEF = 10
MOST_FOR_A_SMALL_BRIEF = 3
MEDIUM_BRIEF = 20
MOST_FOR_A_MEDIUM_BRIEF = 5

#: The marks an item opens with.
ASKED = "[asked]"
BEYOND = "[beyond]"
#: The fewest words of a quote that can show the brief asks for something.
_QUOTE_WORDS = 3


def enabled() -> bool:
    return is_on("ADVICE_SIZED_TO_THE_BRIEF", ON_BY_DEFAULT)


def _criteria_count(brief_text: str) -> int:
    from app.agents.specialist_advice import _criteria_of

    return len(_criteria_of(brief_text))


def most_items(role: str, brief_text: str) -> int:
    """How many items `role` may give for this brief: the full cap when the switch is off, or for the testing role."""
    from app.agents.specialist_advice import MOST_RECOMMENDATIONS

    if not enabled() or role == "testing":
        return MOST_RECOMMENDATIONS
    criteria = _criteria_count(brief_text)
    if criteria <= SMALL_BRIEF:
        return MOST_FOR_A_SMALL_BRIEF
    if criteria <= MEDIUM_BRIEF:
        return MOST_FOR_A_MEDIUM_BRIEF
    return MOST_RECOMMENDATIONS


def request_note(role: str, brief_text: str) -> str:
    """What an adviser's request adds when the switch is on, or ""."""
    if not enabled():
        return ""
    criteria = _criteria_count(brief_text)
    return (
        f"\n\n{SAID}: this brief has {criteria} acceptance criteria, so give at most {most_items(role, brief_text)} "
        f"recommendations - only those that change what is built or how it is proven. Open each one with "
        f"{ASKED} followed by the brief's own words it serves, in double quotes, when the brief asks for it; or with "
        f"{BEYOND} when the brief does not ask for it. Something the brief does not ask for is advised only where "
        "the product cannot meet a criterion without it."
    )


def architect_rule() -> str:
    """What the architect and the part writers are told of the marks when the switch is on, or ""."""
    if not enabled():
        return ""
    return (
        f"{SAID}: an item marked {BEYOND} is declined unless the brief needs it. To adopt one, its decision line "
        "quotes the brief's own words that need it, in double quotes: BE-3: adopted - configuration - brief: "
        f"\"<the brief's words>\". An item marked {BEYOND} adopted without such a quote is recorded as declined.\n"
    )


def sized(items: list[str], role: str, brief_text: str) -> list[str]:
    """`items` cut to this brief's cap, the items the brief asks for first; unchanged when the switch is off."""
    if not enabled():
        return items
    most = most_items(role, brief_text)
    ordered = [item for item in items if not _beyond(item)] + [item for item in items if _beyond(item)]
    if len(ordered) > most:
        logger.info("%s: the %s adviser's %d items cut to %d", SAID, role, len(items), most)
    return ordered[:most]


def _beyond(item: str) -> bool:
    return str(item).lstrip().lower().startswith(BEYOND)


def _flat(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _quotes_the_brief(line: str, brief_text: str) -> bool:
    """Whether `line` quotes words of the brief: a quoted passage of at least `_QUOTE_WORDS` words found in it."""
    brief = f" {_flat(brief_text)} "
    for quoted in re.findall(r"[\"“]([^\"”]+)[\"”]", str(line or "")):
        words = _flat(quoted)
        if len(words.split()) >= _QUOTE_WORDS and f" {words} " in brief:
            return True
    return False


def with_items_beyond_the_brief_declined(specification: Any, advice: dict[str, list[str]] | None,
                                         brief_text: str) -> Any:
    """`specification` with each adopted item marked beyond the brief, whose line quotes no line of the brief,
    recorded as declined. Unchanged when the switch is off or nothing is to change. Never raises."""
    if not enabled() or not advice or not hasattr(specification, "model_copy"):
        return specification
    try:
        from app.agents.specialist_advice import _numbered

        beyond = {ident for _, ident, text in _numbered(advice) if _beyond(text)}
        lines = [str(line) for line in getattr(specification, "specialist_advice_decisions", None) or []]
        changed = []
        kept = []
        for line in lines:
            found = re.match(r"\s*\[?([A-Z]{2,3}-\d+)\]?\s*[:\-–—]\s*(.*)$", line)
            if (found and found.group(1) in beyond and re.match(r"\(?adopted", found.group(2), re.I)
                    and not _quotes_the_brief(line, brief_text)):
                kept.append(f"{found.group(1)}: declined - beyond the brief, and no line of the brief quoted that "
                            "needs it")
                changed.append(found.group(1))
            else:
                kept.append(line)
        if not changed:
            return specification
        logger.info("%s: adopted beyond the brief with no line of it quoted, recorded as declined: %s", SAID,
                    ", ".join(changed))
        return specification.model_copy(update={"specialist_advice_decisions": kept})
    except Exception:  # noqa: BLE001 - the decisions stand as written
        logger.warning("%s: the advice decisions could not be checked", SAID, exc_info=True)
        return specification


__all__ = ["ASKED", "BEYOND", "ON_BY_DEFAULT", "SAID", "architect_rule", "enabled", "most_items", "request_note",
           "sized", "with_items_beyond_the_brief_declined"]
