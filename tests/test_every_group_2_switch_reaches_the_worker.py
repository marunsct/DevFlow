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

#: Switches built and not yet turned on by the owner, each off in compose and
#: in its code. Emptied 2026-10-23 08:08 JST, when the owner turned plan QM.2
#: (`MUTATION_GUIDED_TESTS`) on as its own measured arm.
#: Built behind a switch left off until its measurement says on (owner rule 2026-10-29: doubtful features wait).
NOT_TURNED_ON_YET: frozenset[str] = frozenset({"OBSERVATION_FOLDING", "BATCH_ACCEPTANCE_AUTHOR", "TARGETED_SUITE_REPAIR"})


def test_every_switch_is_passed_through_and_defaults_on():
    for name in SWITCHES:
        found = re.search(rf"^  {name}: \$\{{{name}:-([a-z]*)\}}$", COMPOSE, re.M)
        assert found, f"{name} does not reach the worker"
        assert found.group(1) == ("off" if name in NOT_TURNED_ON_YET else "on"), name


def test_the_switches_not_turned_on_yet_are_switches_off_in_their_code_too():
    from app.observability.provenance import switch

    for name in NOT_TURNED_ON_YET:
        assert name in SWITCHES, name
        assert switch(SWITCHES[name]).ON_BY_DEFAULT is False, name


def test_mutation_guided_tests_are_on_in_compose_and_off_in_code():
    """On as a measured arm by the owner (2026-10-23); its code default stays off, as every switch's does."""
    from app.observability.provenance import switch

    assert re.search(r"^  MUTATION_GUIDED_TESTS: \$\{MUTATION_GUIDED_TESTS:-on\}$", COMPOSE, re.M)
    assert switch(SWITCHES["MUTATION_GUIDED_TESTS"]).ON_BY_DEFAULT is False
