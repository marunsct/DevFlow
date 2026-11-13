"""A dispute ruling that calls a test wrong in its own words is taken, held to its test's own criterion - built in.

Measured on 11-13: three right rulings on tests signing up one name in 40 calls, and one on a lookup by text of only
spaces (the product then shipped failing a hidden test), were refused as quoting what the standard does not say.
"""
import os
from unittest import mock

from app import switches
from app.agents import suite_dispute as sd


def test_it_is_built_in_and_on_with_nothing_set():
    assert "DISPUTE_QUOTES_THE_CRITERION" in switches.BUILT_IN
    with mock.patch.dict(os.environ, {"DISPUTE_QUOTES_THE_CRITERION": ""}):
        assert sd.criterion_quoted_switch.enabled() is True
    with mock.patch.dict(os.environ, {"DISPUTE_QUOTES_THE_CRITERION": "off"}):
        assert sd.criterion_quoted_switch.enabled() is False
