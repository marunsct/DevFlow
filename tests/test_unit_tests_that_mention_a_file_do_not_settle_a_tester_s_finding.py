"""A defect no test was raised from is not settled by unit tests that merely mention its file (LF.1443).

Measured on a medium run (deep review 2026-11-25, decisions finding 4): the tester's "JWT HMAC key is 31 bytes" was
fixed in `auth.py` and settled "its own tests still fail, measured after the fix" - on nine `tests.test_auth` cases
that failed on another defect's mapper error. The fix was counted as failed. On an earlier run five tester findings
with no criterion were recorded `fixed` on unit tests that only named their files and came back 6 hours later. The
snapshot is the run's real `ci.json` "after defect_fix_2_batch".
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.graph.workflow import UNIT_TESTS_FAIL, _the_defect_s_tests_in
from app.sprint import Defect

CAPTURED = Path(__file__).parent / "captured" / "ci-after-a-fix-batch-fastapi.json"
LABEL = "after defect_fix_2_batch"
AUTH = "task-management-dashboard/task_management_dashboard/auth.py"


def _root(tmp_path: Path) -> Path:
    (tmp_path / ".harness").mkdir()
    shutil.copy(CAPTURED, tmp_path / ".harness" / "ci.json")
    return tmp_path


def _defect(description: str, **fields) -> Defect:
    return Defect(description=description, severity="major", reproduction_steps="read auth.py",
                  expected_behavior="a key of at least 32 bytes", actual_behavior="the default key is 31 bytes",
                  owner="security_reliability", affected_files=[AUTH], source="test round", **fields)


def test_a_tester_s_finding_with_no_test_behind_it_is_unverified_not_failed(tmp_path):
    root = _root(tmp_path)
    defect = _defect("JWT HMAC key is 31 bytes, below the 32-byte minimum recommended for SHA256 (RFC 7518)")

    assert _the_defect_s_tests_in(str(root), LABEL, defect) is None


def test_a_defect_raised_from_the_failing_unit_tests_is_still_judged_by_them(tmp_path):
    root = _root(tmp_path)
    defect = _defect(f"{UNIT_TESTS_FAIL} 9 of 32 fail: sqlalchemy.exc.InvalidRequestError")

    assert _the_defect_s_tests_in(str(root), LABEL, defect) is False
