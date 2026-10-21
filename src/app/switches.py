"""On/off switches for features measured before they are trusted (plans MF.4, MF.5).

A feature behind a switch ships off: its module's `ON_BY_DEFAULT` says so, and
the environment variable of the switch's name - `on`/`off` - overrides it for
a Measure arm. `observability.provenance.SWITCHES` lists every switch, so each
run's KPI row says which were on.
"""

from __future__ import annotations

import os

_ON = ("1", "on", "true", "yes")
_OFF = ("0", "off", "false", "no")


def is_on(name: str, default: bool) -> bool:
    """Whether switch `name` is on: its environment variable when set to on or off, else `default`."""
    value = str(os.environ.get(name) or "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return default


__all__ = ["is_on"]
