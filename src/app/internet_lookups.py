"""The user's per-run choice of what the agents may look up on the internet (plan WL.3).

Three values, chosen when a run starts and kept as the run's own switch settings (`switches.for_the_run`), so the
run keeps the value it started with whatever the admin page says later:

- ``off``: nothing is looked up - no stuck-error lookup (`WEB_LOOKUP_WHEN_STUCK` off) and the web search and page
  reader never offered (`WEB_TOOLS_OFFERED` off). Package metadata stays: the package registries (versions and
  installs) and a library's official documentation (`read_docs`, the documentation servers) are how a product is
  built at all, so they are not "lookups".
- ``when_stuck``: the harness looks up a stuck fixer's error (plan WL.4); the web tools are not offered.
- ``always``: as ``when_stuck``, and the web search and page reader are offered to every stage that reads
  documentation, even when tool lists are lean.

A run started with no choice follows the deployment's switches, as every run did before the choice existed.
"""

from __future__ import annotations

from typing import Literal, Mapping

Choice = Literal["off", "when_stuck", "always"]
CHOICES: tuple[str, ...] = ("off", "when_stuck", "always")
#: What the new-run form opens with: the web tools always (owner 2026-11-23).
DEFAULT: Choice = "always"

#: The switches each choice sets for the run.
_SWITCHES_OF: dict[str, dict[str, bool]] = {
    "off": {"WEB_LOOKUP_WHEN_STUCK": False, "WEB_TOOLS_OFFERED": False},
    "when_stuck": {"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": False},
    "always": {"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": True},
}


#: The switches a choice is kept as.
_CHOSEN: tuple[str, ...] = ("WEB_LOOKUP_WHEN_STUCK", "WEB_TOOLS_OFFERED")


def switches_for(choice: str) -> dict[str, bool]:
    """The run's own switch settings `choice` stands for; ValueError for a value that is not one of `CHOICES`."""
    if choice not in _SWITCHES_OF:
        raise ValueError(f"Not an internet lookups choice: {choice!r}")
    return dict(_SWITCHES_OF[choice])


def choice_of(overrides: Mapping[str, bool] | None) -> str | None:
    """The choice a run's own switch settings say it was started with, or None when they name none of them."""
    found = {name: bool((overrides or {})[name]) for name in _CHOSEN if name in (overrides or {})}
    for choice, switches in _SWITCHES_OF.items():
        if found == switches:
            return choice
    return None


def chosen_for_the_run() -> str | None:
    """The choice the current run was started with, from its own switch settings; None outside a run or with none.

    A switch that offers a lookup of its own (`WEB_TOOLS_AFTER_TWO_FAILED_FIXES`) reads it, so "off" stays off."""
    from app.switches import for_the_run

    own = {name: value for name in _CHOSEN if (value := for_the_run(name)) is not None}
    return choice_of(own) if own else None


__all__ = ["CHOICES", "DEFAULT", "Choice", "choice_of", "chosen_for_the_run", "switches_for"]
