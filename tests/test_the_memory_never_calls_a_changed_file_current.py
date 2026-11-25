"""The project memory's opening note never calls a file current that a later note says has changed (deep review
2026-11-25, item 8).

Measured: in 675 of 1,089 requests carrying both notes, one file was named in the opening "[Already in front of you,
whole and current ... Reading any of them returns nothing new]" and in the closing "[Project memory update] Changed
since the project memory was taken". The files and the closing note are a real acceptance author's request.
"""

from __future__ import annotations

import re

from app.agents import project_memory

HELD = ["docs/acceptance_criteria.md", "docs/product_intake.md", "docs/technology_stack.md",
        "notes-api/acceptance/service.cjs", "notes-api/package.json", "notes-api/playwright.config.js",
        "notes-api/src/app.js", "notes-api/src/index.js", "notes-api/start.sh", "notes-api/acceptance/create.spec.js",
        "notes-api/acceptance/delete.spec.js", "notes-api/acceptance/fetch.spec.js",
        "notes-api/acceptance/health.spec.js", "notes-api/acceptance/integration.spec.js",
        "notes-api/acceptance/list.spec.js", "notes-api/acceptance/persistence.spec.js",
        "notes-api/acceptance/startsh.spec.js", "notes-api/acceptance/update.spec.js",
        "notes-api/acceptance/validation.spec.js"]
CLOSING = ("[Project memory update]\nChanged since the project memory was taken (read for the current text): "
           "notes-api/acceptance/startsh.spec.js (31 lines now)")
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_file_changed_since_is_not_called_current_at_the_opening():
    opening = project_memory.files_held_line(HELD)

    assert "`notes-api/acceptance/startsh.spec.js`" in opening and "startsh.spec.js" in CLOSING
    assert not re.search(r"\bcurrent\b", opening)
    assert "when this stage began" in opening
    # And it says where a change is named, so the two notes read as one.
    assert "at the end of a request" in opening
    assert not BANNED.search(opening)
