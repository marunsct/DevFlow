"""On/off switches for features measured before they are trusted (plans MF.4, MF.5).

A feature behind a switch ships off: its module's `ON_BY_DEFAULT` says so, and
the environment variable of the switch's name - `on`/`off` - overrides it for
a Measure arm. `observability.provenance.SWITCHES` lists every switch, so each
run's KPI row says which were on.

An administrator can set a switch on the admin page (`/admin`). That setting is
stored with the other runtime settings and beats the environment, in every
process, within the settings cache's few seconds. A switch nobody set follows
the environment as before. Processes read the stored settings only when
`SWITCH_OVERRIDES_FROM_SETTINGS` is on (the compose file turns it on), so a
test or a script outside the services never queries a database for a switch.
"""

from __future__ import annotations

import os

_ON = ("1", "on", "true", "yes")
_OFF = ("0", "off", "false", "no")


def stored(name: str) -> bool | None:
    """The admin page's setting for switch `name`, or None when it has none or settings are not read here."""
    if str(os.environ.get("SWITCH_OVERRIDES_FROM_SETTINGS") or "").strip().lower() not in _ON:
        return None
    try:
        from app.server.runtime_settings import switch_overrides

        return switch_overrides().get(name)
    except Exception:  # noqa: BLE001 - the environment decides when the settings cannot be read
        return None


def from_the_environment(name: str) -> bool | None:
    """The switch's environment variable as on (True) or off (False), or None when unset or not on/off."""
    value = str(os.environ.get(name) or "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return None


def is_on(name: str, default: bool) -> bool:
    """Whether switch `name` is on: the admin page's setting, else its environment variable, else `default`."""
    setting = stored(name)
    if setting is not None:
        return setting
    environment = from_the_environment(name)
    return default if environment is None else environment


__all__ = ["from_the_environment", "is_on", "stored"]
