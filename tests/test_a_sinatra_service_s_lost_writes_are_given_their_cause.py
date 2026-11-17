"""A Sinatra service's lost concurrent writes reach the fixer with their cause.

Measured on one run: the store lived in a helper's `@store ||= NotesStore.new`. Sinatra makes a new app object for each
request, so every request read the file afresh and ten creates at once lost all but one; the fix locked the write alone
and the defect came back after a re-plan.
"""
from __future__ import annotations

import re

from app.acceptance.concurrent_write_probe import CONCURRENT_WRITES_LOST
from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_probe_s_defect_is_given_the_per_request_app_object_as_its_cause(tmp_path):
    contract.write(tmp_path, pack_named("ruby-sinatra-api"), "notes-api", "Notes")
    text = f"{CONCURRENT_WRITES_LOST} `POST /notes` was sent 10 creates at once; 1 was kept."

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description=text, severity="major", reproduction_steps="10 creates at once", expected_behavior="10 kept",
        actual_behavior=text, affected_files=[], owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "a new app object for each request" in defect.actual_behavior
    assert "the helper every route calls return that one store" in defect.actual_behavior  # a shared store unused
    assert not BANNED.search(defect.actual_behavior)
