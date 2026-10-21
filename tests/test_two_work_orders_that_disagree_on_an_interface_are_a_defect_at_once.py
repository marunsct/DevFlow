"""Two work orders of one batch that disagree on an interface become a defect at the CI gate (plan CM.3, its parallel half).

Behind `INTERFACE_CLASH_CHECK`, off until measured: one work order removed a
definition while another, side by side, still called it, and the break came
back rounds later as a failing test.
"""
from __future__ import annotations

import inspect
import os
import re
import subprocess
from types import SimpleNamespace
from unittest import mock

from app.agents import interface_clashes
from app.graph import engineering

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"INTERFACE_CLASH_CHECK": "on"}


def _batch(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "store.py").write_text("def load_items():\n    return []\n")
    (tmp_path / "app" / "routes.py").write_text("x = 1\n")
    for args in (("init", "-q"), ("add", "-A"), ("-c", "user.email=h@example.com", "-c", "user.name=h", "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    (tmp_path / "app" / "store.py").write_text("def fetch_items():\n    return []\n")
    (tmp_path / "app" / "routes.py").write_text("from app.store import load_items\n\ndef index():\n    return load_items()\n")
    return {
        "specialist_backend_0": SimpleNamespace(changed_files=["app/store.py"]),
        "specialist_ui_ux_1": SimpleNamespace(changed_files=["app/routes.py"]),
    }


def test_on_a_removed_name_another_work_order_still_uses_is_a_defect_owned_by_that_work_order(tmp_path):
    outputs = _batch(tmp_path)
    with mock.patch.dict(os.environ, ON):
        found = interface_clashes.defects(tmp_path, outputs, interface_clashes.role_of)

    assert len(found) == 1
    defect = found[0]
    assert "`load_items` was removed from `app/store.py` by specialist_backend_0" in defect.description
    assert defect.owner == "ui_ux" and defect.affected_files == ["app/routes.py", "app/store.py"]
    assert not BANNED.search(defect.description + defect.expected_behavior + defect.actual_behavior)


def test_off_or_with_no_other_user_there_is_no_defect(tmp_path):
    outputs = _batch(tmp_path)
    with mock.patch.dict(os.environ, {"INTERFACE_CLASH_CHECK": ""}):
        assert interface_clashes.clashes(tmp_path, outputs) == []
    (tmp_path / "app" / "routes.py").write_text("from app.store import fetch_items\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == []


def test_a_role_is_read_whole_from_a_builder_s_stage():
    assert interface_clashes.role_of("specialist_ui_ux_1") == "ui_ux"
    assert interface_clashes.role_of("specialist_backend_0") == "backend"
    assert interface_clashes.role_of("defect_fix_1_0") == ""


def test_the_ci_gate_checks_before_it_commits_and_files_them():
    source = inspect.getsource(engineering.ci_gate)
    assert source.index("interface_clashes.defects(") < source.index("ci.commit(root")
    assert '*raised_by("interface clash", clashed)' in source
