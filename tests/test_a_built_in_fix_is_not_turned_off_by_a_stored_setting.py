"""A built-in fix is not turned off by a stored admin setting or a run's setting; only its host variable can.

Found in the launch review: `is_on` read the run's setting and the stored admin setting before `BUILT_IN`, so a row
stored before the fix was built in turned a bug fix off with nothing in the run's record to say so.
"""
from __future__ import annotations

from unittest import mock

from app import switches


def test_stored_and_run_settings_do_not_reach_a_built_in_fix(monkeypatch):
    name = sorted(switches.BUILT_IN)[0]
    monkeypatch.delenv(name, raising=False)
    with mock.patch.object(switches, "stored", return_value=False), \
            mock.patch.object(switches, "for_the_run", return_value=False):
        assert switches.is_on(name, False) is True


def test_the_host_variable_still_turns_one_off(monkeypatch):
    name = sorted(switches.BUILT_IN)[0]
    monkeypatch.setenv(name, "off")
    assert switches.is_on(name, True) is False


def test_an_experiment_still_follows_its_stored_setting(monkeypatch):
    name = sorted(set(switches.EXPERIMENTS) - set(switches.BUILT_IN))[0]
    monkeypatch.delenv(name, raising=False)
    with mock.patch.object(switches, "stored", side_effect=lambda n: True if n == name else None), \
            mock.patch.object(switches, "for_the_run", return_value=None):
        assert switches.is_on(name, False) is True
