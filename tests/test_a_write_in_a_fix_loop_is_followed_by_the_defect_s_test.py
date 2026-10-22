"""A write in a fix stage is followed by the defect's own tests, and the write's reply says how they went (plan AY step 3).

Behind `VERIFY_AFTER_WRITE`, off until measured. A fixer ran the suite
itself, or not at all, to learn what the harness could tell it after each
write; one took 42 calls on one defect.
"""
from __future__ import annotations

import inspect
import os
import re
from types import SimpleNamespace
from unittest import mock

from langchain_core.messages import ToolMessage

from app.agents import role_agent
from app.graph import verify_after_write as vaw
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"VERIFY_AFTER_WRITE": "on"}


def _written(status="success"):
    return ToolMessage(content="Wrote app/main.py (12 lines).", tool_call_id="c1", status=status)


def test_a_watched_write_says_whether_the_defect_s_tests_pass_now():
    outcomes = iter([False, True])
    with mock.patch.dict(os.environ, ON), vaw.watching("run", "defect_fix_1_0", lambda: next(outcomes)):
        first = vaw.after_a_write("edit_artifact", _written(), "run", "defect_fix_1_0")
        second = vaw.after_a_write("write_artifact", _written(), "run", "defect_fix_1_0")
    assert first.content.endswith(vaw.FAILING) and second.content.endswith(vaw.PASSED)
    assert "give your answer now" in vaw.PASSED and "other defects" in vaw.PASSED
    assert not BANNED.search(vaw.PASSED + vaw.FAILING)


def test_reads_failed_writes_other_stages_and_off_are_left_as_they_were():
    ran = []
    with mock.patch.dict(os.environ, ON), vaw.watching("run", "defect_fix_1_0", lambda: ran.append(1) or True):
        assert vaw.after_a_write("read_file", _written(), "run", "defect_fix_1_0").content == "Wrote app/main.py (12 lines)."
        assert vaw.after_a_write("edit_artifact", _written("error"), "run", "defect_fix_1_0").content.endswith("lines).")
        assert vaw.after_a_write("edit_artifact", _written(), "run", "specialist_backend_0").content.endswith("lines).")
    with mock.patch.dict(os.environ, {"VERIFY_AFTER_WRITE": ""}), vaw.watching("run", "defect_fix_1_0", lambda: ran.append(1) or True):
        assert vaw.after_a_write("edit_artifact", _written(), "run", "defect_fix_1_0").content.endswith("lines).")
    assert ran == []


def test_the_checks_per_stage_are_bounded():
    ran = []
    with mock.patch.dict(os.environ, ON), vaw.watching("run", "defect_fix_1_0", lambda: ran.append(1) or False):
        for _ in range(vaw.MOST_CHECKS + 3):
            vaw.after_a_write("edit_artifact", _written(), "run", "defect_fix_1_0")
    assert len(ran) == vaw.MOST_CHECKS


def test_the_middleware_passes_a_result_through_and_the_fix_stage_and_agents_use_it():
    middleware = vaw.build_middleware()
    request = SimpleNamespace(tool_call={"name": "edit_artifact", "id": "c1"})
    assert middleware.wrap_tool_call(request, lambda r: _written()).content == "Wrote app/main.py (12 lines)."
    assert "verify_after_write.watching(" in inspect.getsource(workflow)
    assert "_verify_after_write_middleware()" in inspect.getsource(role_agent)


def test_a_write_that_did_not_happen_runs_no_check():
    """An edit whose text was not found answers as a successful message with an error in it."""
    import os as _os
    from unittest import mock as _mock

    from langchain_core.messages import ToolMessage

    from app.graph import verify_after_write as module

    ran = []
    with _mock.patch.dict(_os.environ, {"VERIFY_AFTER_WRITE": "on"}), \
         module.watching("run", "defect_fix_1_0", lambda: ran.append(1) or False):
        for content in ('{"error": "Could not find that text"}', "Refusing this write: unchanged"):
            message = ToolMessage(content=content, tool_call_id="1")
            assert module.after_a_write("edit_artifact", message, "run", "defect_fix_1_0").content == content
        module.after_a_write("edit_artifact", ToolMessage(content='{"status": "edited"}', tool_call_id="2"), "run", "defect_fix_1_0")
    assert ran == [1], "only the write that happened is measured"
