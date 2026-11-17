"""Fixers working side by side in one batch never write the same file (LR.15).

Measured on one run: two fixers of one batch both rewrote the same database module, and each write then failed on the
other's until both reached their call budgets.
"""
from __future__ import annotations

import inspect
import re

from app.graph import batch_file_claims as claims
from workflow_nodes import workflow_source

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


def test_the_batch_fixer_holds_and_the_refusal_bans_the_product_s_nouns():
    source = workflow_source()
    worker = source[source.index("def defect_fix_worker_node"):]
    assert "batch_file_claims.holding(" in worker[:2500]
    assert not BANNED.search(claims.REFUSED + inspect.getsource(claims.build_middleware))
