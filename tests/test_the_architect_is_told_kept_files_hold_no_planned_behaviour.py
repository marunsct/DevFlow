"""The layout every stage reads says the harness's kept files hold nothing the product plans.

Measured on three runs: the specification put creating the data directory and checking the port in the pack's
`start.sh`, and signal handling in its kept start file; the reviews then sent the sprint back for it.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import layout_facts
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_pack_with_kept_files_says_they_hold_no_planned_behaviour():
    lines = layout_facts(pack_named("node-hono-native-api"), "notes-api", None)
    rule = [line for line in lines if "do what they do now and nothing more" in line]
    assert rule and "the product's own files" in rule[0] and "shutdown" in rule[0]
    assert not BANNED.search(rule[0])
    assert lines.index(rule[0]) > next(i for i, line in enumerate(lines) if "Kept by the harness" in line)
