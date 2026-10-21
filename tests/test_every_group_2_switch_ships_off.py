"""Every group 2 switch ships off and turns on and off by its own name (plans MF.4, MF.5).

A feature is trusted only once measured, so each one built ahead of its Measure
arm is behind a switch that is off by default, read from the environment
variable of its name, and listed for the KPI rows.
"""
from __future__ import annotations

import importlib
import os
from unittest import mock

import pytest

from app.observability.provenance import SWITCHES, switches_on


@pytest.mark.parametrize("name,module", sorted(SWITCHES.items()))
def test_the_switch_is_off_by_default_and_follows_its_variable(name, module):
    loaded = importlib.import_module(module)

    assert loaded.ON_BY_DEFAULT is False
    with mock.patch.dict(os.environ, {name: ""}):
        assert loaded.enabled() is False
    with mock.patch.dict(os.environ, {name: "on"}):
        assert loaded.enabled() is True and name in switches_on()
    with mock.patch.dict(os.environ, {name: "off"}):
        assert loaded.enabled() is False
