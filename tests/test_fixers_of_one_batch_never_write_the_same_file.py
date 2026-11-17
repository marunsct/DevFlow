"""Fixers working side by side in one batch never write the same file (LR.15).

Measured on one run: two fixers of one batch both rewrote the same database module, and each write then failed on the
other's until both reached their call budgets.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph import batch_file_claims as claims

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
WRITE = {"relative_path": "api/db.py", "content": "x"}


def test_the_first_writer_holds_the_file_and_the_other_is_refused_until_it_ends():
    with claims.holding("run-1", "defect_fix_1_0"):
        with claims.holding("run-1", "defect_fix_1_6"):
            assert claims.owner_of("run-1", "defect_fix_1_0", "write_artifact", WRITE) == ""
            claims.claim("run-1", "defect_fix_1_0", "write_artifact", WRITE)
            assert claims.owner_of("run-1", "defect_fix_1_6", "edit_artifact", WRITE) == "defect_fix_1_0"
            assert claims.owner_of("run-1", "defect_fix_1_0", "edit_artifact", WRITE) == ""
            assert claims.owner_of("run-1", "defect_fix_1_6", "edit_artifact", {"relative_path": "api/app.py"}) == ""
        # The holder ended: the file is free.
    with claims.holding("run-1", "defect_fix_1_6"):
        assert claims.owner_of("run-1", "defect_fix_1_6", "edit_artifact", WRITE) == ""


def test_a_stage_outside_a_batch_and_another_run_are_untouched():
    with claims.holding("run-1", "defect_fix_1_0"):
        claims.claim("run-1", "defect_fix_1_0", "write_artifact", WRITE)
        assert claims.owner_of("run-1", "defect_fix", "write_artifact", WRITE) == ""
        assert claims.owner_of("run-2", "defect_fix_1_6", "write_artifact", WRITE) == ""


def test_a_batch_fixer_holds_what_it_writes_while_it_runs_and_no_longer(tmp_path):
    import the_fix_stage

    def another_fixer_writes_after_this_one(stage_name):
        with claims.holding("r", "defect_fix_2_9"):
            claims.claim("r", stage_name, "write_artifact", WRITE)
            return claims.owner_of("r", "defect_fix_2_9", "edit_artifact", WRITE)

    state = the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(), the_fix_stage.a_defect("The total is wrong"),
                                  __fix_index=1)

    _, seen = the_fix_stage.run(tmp_path, state, node="defect_fix_worker", during=another_fixer_writes_after_this_one)

    assert seen.during == ["defect_fix_2_1"]
    with claims.holding("r", "defect_fix_2_9"):
        assert claims.owner_of("r", "defect_fix_2_9", "edit_artifact", WRITE) == ""


def test_the_refusal_a_second_fixer_reads_names_the_file_and_its_holder_and_no_product_noun(monkeypatch):
    from langchain_core.messages import ToolMessage

    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-1")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda default="": "defect_fix_1_6")
    written = []
    middleware = claims.build_middleware()

    with claims.holding("run-1", "defect_fix_1_0"), claims.holding("run-1", "defect_fix_1_6"):
        claims.claim("run-1", "defect_fix_1_0", "write_artifact", WRITE)
        refused = middleware.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "edit_artifact", "args": WRITE, "id": "call-1"}),
            lambda request: written.append(request) or ToolMessage(content="written", tool_call_id="call-1"),
        )

    assert written == [] and refused.status == "error"
    assert "`api/db.py`" in refused.content and "defect_fix_1_0" in refused.content
    assert not BANNED.search(refused.content)
