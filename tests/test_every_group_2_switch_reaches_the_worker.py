"""Every group 2 switch is passed to the app and the worker, so a subsystem can be measured by setting it on the host.

None was: the compose file named no switch, so each stayed at its coded default
whatever the host set. Off unless set, but for the two that change nothing the
model does during a run (owner, 2026-10-22). Since 18:40 JST that day every
switch defaults on (owner: a baseline with all the improvements, features
turned off later to measure the unproven ones); the default lives here so a
later deploy cannot turn one off by leaving the host unset.

Except a switch the owner has not turned on yet: it reaches the worker the
same way and defaults off, so a deploy cannot turn it on by leaving the host
unset either.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.observability.provenance import SWITCHES

COMPOSE = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()

#: Since 2026-10-29 (owner: no switch for a bug; premium features bundled over a free base; experiments off until
#: measured) the deployed switches are the bundles and the experiments; every feature is one of those or built in.


def test_the_operated_switches_reach_the_worker_bundles_on_and_experiments_off():
    from app import switches

    for name in switches.BUNDLES:
        assert re.search(rf"^  {name}: \$\{{{name}:-on\}}$", COMPOSE, re.M), name
    for name in switches.EXPERIMENTS:
        deployed = "on" if name in switches.EXPERIMENTS_ON else "off"
        assert re.search(rf"^  {name}: \$\{{{name}:-{deployed}\}}$", COMPOSE, re.M), name
    assert set(switches.EXPERIMENTS_ON) <= set(switches.EXPERIMENTS)


def test_every_feature_is_built_in_bundled_or_an_experiment_once_and_none_is_deployed_on_its_own():
    from app import switches

    places = [*switches.BUILT_IN, *(m for members in switches.BUNDLES.values() for m in members), *switches.EXPERIMENTS]
    assert sorted(places) == sorted(SWITCHES)
    for name in SWITCHES:
        if name not in switches.EXPERIMENTS:
            assert not re.search(rf"^  {name}: ", COMPOSE, re.M), name


def test_a_built_in_fix_is_on_with_nothing_set_and_a_feature_follows_its_bundle(monkeypatch):
    from app import switches

    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.delenv("STALL_RULE", raising=False)
    assert switches.is_on("STALL_RULE", False) is True
    monkeypatch.delenv("MUTATION_GUIDED_TESTS", raising=False)
    monkeypatch.setenv("PREMIUM_DEEP_VERIFICATION", "off")
    assert switches.is_on("MUTATION_GUIDED_TESTS", True) is False
    monkeypatch.setenv("PREMIUM_DEEP_VERIFICATION", "on")
    assert switches.is_on("MUTATION_GUIDED_TESTS", False) is True


def test_the_experiments_are_off_in_their_code_too():
    from app import switches
    from app.observability.provenance import switch

    for name in switches.EXPERIMENTS:
        assert switch(SWITCHES[name]).ON_BY_DEFAULT is False, name
