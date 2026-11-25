"""What a page shows when there is nothing yet, while a request is on its way, and when one fails, as lines a test can
find (plan PQ.8, behind `INTERFACE_STATES_AS_CRITERIA`, off until measured).

Read in eight stored products (`reports/audits/2026-11-25-product-quality-ui-db-api.md`): the interface is built to
what the tests can find, and the UI/UX advice's "what is shown when there is nothing yet" reached the specification as
prose, if at all. The best page of the set showed nothing on a failed request and no busy state while one ran, and put
its empty state inside the list; two others had no empty state, one specification deferring it outright. So, for a
product with a page, the architect is asked to name each of the three states in `interface_design` as a line with an
ARIA role and the words shown, an element of its own outside any list of records (a hidden check counting the items of
a list must not count it), and the specification is sent back once when a state is missing. The acceptance author and
the builders are given `interface_design` whole (`app.acceptance.api_reference`), so each line is one they can find.

Presentation only: none of it refuses or limits what a person may do, so it adds nothing the brief rules out.
"""
from __future__ import annotations

import re
from typing import Any

from app.switches import is_on

#: `INTERFACE_STATES_AS_CRITERIA` set to on or off overrides this.
ON_BY_DEFAULT = False

#: The product kinds with a page.
_KINDS_WITH_A_PAGE = frozenset({"browser_app", "fullstack"})

#: Said to the architect and to the writer of `interface_design`, for a product with a page.
RULE = (
    "\n\nThis product has a page. In `interface_design`, name what a person sees in three states, one line each, "
    "written `Empty: ...`, `Busy: ...` and `Failed: ...`: when there is nothing yet to show, while a request is on "
    "its way, and when a request fails. Each line names the view it belongs to, the element's ARIA role (for "
    "example `status` for the empty and busy states, `alert` for a failure) and the exact words it shows in double "
    "quotes - a failure's words say what to do next. Each is an element of its own, outside any list of records, so "
    "a count of the records never includes it, and it is gone once the state is over. These lines say what is "
    "shown, never what is refused: every control stays usable in every state."
)

#: Each state, and the words a line naming it uses.
STATES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("Empty", "when there is nothing yet to show",
     re.compile(r"\bempty\b|\bnothing (?:yet|to show)\b|\bno \w+(?: \w+)? yet\b", re.I)),
    ("Busy", "while a request is on its way",
     re.compile(r"\bbusy\b|\bloading\b|\bin flight\b|\bon its way\b|\bpending\b|\bin progress\b|\bwaiting\b", re.I)),
    ("Failed", "when a request fails",
     re.compile(r"\bfail(?:s|ed|ure)?\b|\berrors?\b|\bunavailable\b|\bcould not\b", re.I)),
)
_A_ROLE = re.compile(r"\brole\b|\baria-live\b", re.I)
_QUOTED_WORDS = re.compile(r"[\"“][^\"”\n]{2,}[\"”]")


def enabled() -> bool:
    return is_on("INTERFACE_STATES_AS_CRITERIA", ON_BY_DEFAULT)


def has_a_page(state: Any) -> bool:
    """Whether the product being built has a page, from the stack chosen and the brief. Never raises."""
    try:
        from app.stacks import product_kind

        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        brief = getattr(state.get("document"), "text", "") or ""
        return product_kind(stack, brief) in _KINDS_WITH_A_PAGE
    except Exception:  # noqa: BLE001 - nothing to judge by: no page assumed
        return False


def applies(state: Any) -> bool:
    """On, and the product has a page."""
    return enabled() and has_a_page(state)


def rule_for(state: Any) -> str:
    """`RULE` when it applies to this run, else ""."""
    return RULE if applies(state) else ""


def missing(specification: Any) -> list[str]:
    """The states (`Empty`, `Busy`, `Failed`) no line of `interface_design` names with a role and the words shown."""
    lines = [" ".join(str(line).split()) for line in getattr(specification, "interface_design", None) or []]
    found = [line for line in lines if _A_ROLE.search(line) and _QUOTED_WORDS.search(line)]
    return [name for name, _, words in STATES if not any(words.search(line) for line in found)]


def repair(states: list[str]) -> str:
    """The revision comment asking for the missing states, and only `interface_design` back."""
    wanted = "; ".join(f"`{name}:` {when}" for name, when, _ in STATES if name in states)
    return (
        "`interface_design` does not name what the page shows " + wanted + ". " + RULE.strip()
        + " The document `docs/technical_specification.md` on disk already holds the completed sections. Return only "
        "`interface_design`, whole, with these lines added; unchanged sections are automatically preserved."
    )


class _InterfaceStates:
    """`INTERFACE_STATES_AS_CRITERIA` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("For a product with a page, the specification names what is shown when there is nothing yet, "
                   "while a request is on its way and when one fails, each a line with an ARIA role and the words "
                   "shown, outside any list; a specification missing one is sent back once. Presentation only.")

    @staticmethod
    def enabled() -> bool:
        return enabled()


interface_states_switch = _InterfaceStates()

__all__ = ["ON_BY_DEFAULT", "RULE", "STATES", "applies", "enabled", "has_a_page", "interface_states_switch", "missing",
           "repair", "rule_for"]
