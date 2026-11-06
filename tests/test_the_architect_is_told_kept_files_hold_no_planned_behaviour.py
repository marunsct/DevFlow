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


def test_the_kept_manifest_scripts_are_named_too():
    """Measured on two runs: both fixers of a failing unit run rewrote the kept `test` script, which was put back."""
    lines = layout_facts(pack_named("node-hono-native-api"), "notes-api", None)
    said = [line for line in lines if "script" in line and "put back" in line]
    assert said and "`test`" in said[0] and "`start`" in said[0] and "never there" in said[0]
    assert not BANNED.search(said[0])


def test_a_short_kept_start_file_is_shown_as_it_is():
    """Measured on a fourth run: told only that `src/main.ts` was kept, the specification had it create the data
    directory - it hands `DATA_DIR` to the product's factory and creates nothing - and the review blocked on it."""
    lines = layout_facts(pack_named("node-hono-native-api"), "notes-api", None)
    shown = [line for line in lines if "`notes-api/src/main.ts` does now" in line]
    assert shown and "factory(process.env.DATA_DIR)" in shown[0] and "Listening on" in shown[0]
    assert "// The named" not in shown[0]  # comments left out
    assert not BANNED.search(shown[0].split("```")[0])


def test_configuration_and_test_runners_are_not_shown():
    lines = layout_facts(pack_named("fullstack-page-fastapi"), "bookmarks", "bookmarks")
    shown = " ".join(line for line in lines if " does now" in line)
    assert "serve-acceptance.mjs" in shown
    assert "playwright.config.js" not in shown and "unit-tests.mjs" not in shown and "vite.config.ts" not in shown
