"""Every group 2 switch is passed to the app and the worker, so a subsystem can be measured by setting it on the host.

None was: the compose file named no switch, so each stayed at its coded default
whatever the host set. Off unless set, but for the two that change nothing the
model does during a run (owner, 2026-10-22). Since 18:40 JST that day every
switch defaults on (owner: a baseline with all the improvements, features
turned off later to measure the unproven ones); the default lives here so a
later deploy cannot turn one off by leaving the host unset.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.observability.provenance import SWITCHES

COMPOSE = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()


def test_every_switch_is_passed_through_and_defaults_on():
    for name in SWITCHES:
        found = re.search(rf"^  {name}: \$\{{{name}:-([a-z]*)\}}$", COMPOSE, re.M)
        assert found, f"{name} does not reach the worker"
        assert found.group(1) == "on", name
