"""The architect is told the setup's `start.sh` already starts the service, so the plan keeps it.

Both Measure gate runs' specifications designed a start.sh of their own; one,
`exec python tasks_api/app.py`, was drafted over the setup's working script and
the product would not start for anyone outside the run.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import layout_facts
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_pack_with_a_start_script_says_it_is_set_up_and_how_it_runs():
    for name in ("python-flask-api", "python-http-api", "node-http-api"):
        facts = "\n".join(layout_facts(pack_named(name), "tasks-api", "tasks_api"))
        line = next(l for l in facts.splitlines() if "start.sh" in l)

        assert "`tasks-api/start.sh` is already set up" in line and "keeps it as it is" in line, name
        assert "{{" not in line and "exec" in line, line
        assert not BANNED.search(line.replace("tasks-api", "").replace("tasks_api", "")), line


def test_a_pack_without_one_says_nothing_of_it():
    facts = "\n".join(layout_facts(pack_named("browser-javascript"), "notes", None))

    assert "start.sh" not in facts
