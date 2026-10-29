"""Every group 2 switch ships off and turns on and off by its own name (plans MF.4, MF.5).

A feature is trusted only once measured, so each one built ahead of its Measure
arm is behind a switch that is off by default, read from the environment
variable of its name, and listed for the KPI rows.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from app.observability.provenance import SWITCHES, switch, switches_on


@pytest.mark.parametrize("name,module", sorted(SWITCHES.items()))
def test_the_switch_is_off_by_default_and_follows_its_variable(name, module):
    """Off in its code; with nothing set a built-in fix is on and a bundled feature follows its bundle (2026-10-29)."""
    from app import switches

    loaded = switch(module)

    assert loaded.ON_BY_DEFAULT is False
    bundle = switches.bundle_of(name)
    with mock.patch.dict(os.environ, {name: "", **({bundle: ""} if bundle else {})}):
        assert loaded.enabled() is (name in switches.BUILT_IN)
    with mock.patch.dict(os.environ, {name: "on"}):
        assert loaded.enabled() is True and name in switches_on()
    with mock.patch.dict(os.environ, {name: "off"}):
        assert loaded.enabled() is False
