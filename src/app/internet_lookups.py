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
#: What the new-run form opens with.
DEFAULT: Choice = "when_stuck"

#: The switches each choice sets for the run.
_SWITCHES_OF: dict[str, dict[str, bool]] = {
    "off": {"WEB_LOOKUP_WHEN_STUCK": False, "WEB_TOOLS_OFFERED": False},
    "when_stuck": {"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": False},
    "always": {"WEB_LOOKUP_WHEN_STUCK": True, "WEB_TOOLS_OFFERED": True},
}


def switches_for(choice: str) -> dict[str, bool]:
    """The run's own switch settings `choice` stands for; ValueError for a value that is not one of `CHOICES`."""
    if choice not in _SWITCHES_OF:
        raise ValueError(f"Not an internet lookups choice: {choice!r}")
    return dict(_SWITCHES_OF[choice])


def choice_of(overrides: Mapping[str, bool] | None) -> str | None:
    """The choice a run's own switch settings say it was started with, or None when they name none of them."""
    found = {name: bool((overrides or {})[name]) for name in ("WEB_LOOKUP_WHEN_STUCK", "WEB_TOOLS_OFFERED")
             if name in (overrides or {})}
    for choice, switches in _SWITCHES_OF.items():
        if found == switches:
            return choice
    return None


__all__ = ["CHOICES", "DEFAULT", "Choice", "choice_of", "switches_for"]
