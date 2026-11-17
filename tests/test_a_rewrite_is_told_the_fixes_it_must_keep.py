"""A defect fixed by a one-call rewrite is told the earlier fixes it must keep, as a fix stage is.

Measured on one run: every fix of a page's list-structure check came through the rewrite, which was never told that
an earlier fix had moved the empty-state message out of the list for another test; it moved it back ten times over.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import rewritten_fixes, workflow

KEPT = ("--- Fixed earlier - keep these fixes ---\n"
        "- [AC-7] An empty list shows no entries - fixed: the empty-state message is a paragraph outside the list\n")


def test_the_rewrite_request_carries_the_fixes_to_keep(tmp_path):
    (tmp_path / "app.js").write_text("const x = 1;\n")
    defect = SimpleNamespace(description="An accessibility check finds a list rule broken", expected_behavior="",
                             actual_behavior="", affected_files=[])
    asked = rewritten_fixes.fix_request(tmp_path, "app.js", defect, "rule: list", None, None, [], [], "", kept=KEPT)
    assert "keep these fixes" in asked and "paragraph outside the list" in asked
    assert "keep these fixes" not in rewritten_fixes.fix_request(tmp_path, "app.js", defect, "rule: list", None, None, [], [])


EARLIER = [{"defect_log": [
    {"state": "fixed", "owner": "ui_ux", "files": ["web/app.js"], "description": "[AC-7] An empty list shows no entries",
     "resolution": "the message is a paragraph outside the list"}]}]


def test_both_rewrite_paths_are_given_them(tmp_path):
    """The candidates after a failed fix, and the single rewrite after them, are each told the fixes to keep."""
    import the_fix_stage
    from app.agents.specialists import SpecialistOutput

    defect = the_fix_stage.a_defect(owner="ui_ux", fix_attempts=1, affected_files=["web/app.js"])
    state = the_fix_stage.a_state(tmp_path, defect, sprint_attempts=EARLIER)
    _, seen = the_fix_stage.run(tmp_path, state, fast=True, candidate_model=SimpleNamespace(name="candidates"),
                                   candidate=None, rewrite=SpecialistOutput(changed_files=["web/app.js"]))

    kept = workflow._the_fixes_to_keep_for(state, defect)
    assert "[AC-7] An empty list shows no entries" in kept
    assert seen.candidates[0]["kept"] == kept
    assert seen.rewrites[0]["kept"] == kept


def test_the_fixes_come_from_earlier_attempts_by_role():
    state = {"sprint_attempts": [{"defect_log": [
        {"state": "fixed", "owner": "ui_ux", "files": ["web/app.js"], "description": "[AC-7] An empty list shows no entries",
         "resolution": "the message is a paragraph outside the list"}]}]}
    defect = SimpleNamespace(affected_files=[], owner="ui_ux")
    assert "[AC-7] An empty list shows no entries" in workflow._the_fixes_to_keep_for(state, defect)
    assert workflow._the_fixes_to_keep_for({}, defect) == ""
