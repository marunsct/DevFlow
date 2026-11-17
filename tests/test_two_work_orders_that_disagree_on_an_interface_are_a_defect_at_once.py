"""Two work orders of one batch that disagree on an interface become a defect at the CI gate (plan CM.3, its parallel half).

Behind `INTERFACE_CLASH_CHECK`, off until measured: one work order removed a
definition while another, side by side, still called it, and the break came
back rounds later as a failing test.
"""
from __future__ import annotations

import os
import re
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from app.agents import interface_clashes
from app.agents.specialists import SpecialistOutput
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
    with mock.patch.dict(os.environ, {"INTERFACE_CLASH_CHECK": "off"}):
        assert interface_clashes.clashes(tmp_path, outputs) == []
    (tmp_path / "app" / "routes.py").write_text("from app.store import fetch_items\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == []


def test_a_role_is_read_whole_from_a_builder_s_stage():
    assert interface_clashes.role_of("specialist_ui_ux_1") == "ui_ux"
    assert interface_clashes.role_of("specialist_backend_0") == "backend"
    assert interface_clashes.role_of("defect_fix_1_0") == ""


def test_the_ci_gate_files_a_clash_in_the_batch_it_commits(tmp_path, monkeypatch):
    """Asked after the commit, the batch's start is the commit itself and nothing has changed since."""
    from app import ci

    outputs = _batch(tmp_path)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    # Running the product's tests is the sandbox's: one snapshot with nothing measured stands in for it.
    monkeypatch.setattr(ci, "take", lambda root, label: ci.Snapshot(label=label))
    monkeypatch.setattr(engineering, "underlined_in_the_batch", lambda state, root, since: [])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": outputs,
             "milestone_plan": SimpleNamespace(delegated_tasks=[])}

    with mock.patch.dict(os.environ, ON):
        update = engineering.ci_gate(state, {"configurable": {}}, None)

    [defect] = update["review_defects"]
    assert defect.source == "interface clash" and "`load_items` was removed from `app/store.py`" in defect.description
    assert defect.owner == "ui_ux"


def test_a_moved_name_or_a_name_of_another_module_is_no_clash(tmp_path):
    """A defect no fixer can settle: a definition moved to another file, or a common name (`get`)
    the other file uses from somewhere else, read as a clash."""
    outputs = _batch(tmp_path)
    (tmp_path / "app" / "items.py").write_text("def load_items():\n    return []\n")
    outputs["specialist_backend_0"].changed_files.append("app/items.py")
    (tmp_path / "app" / "routes.py").write_text("from app.items import load_items\n\ndef index():\n    return load_items()\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == [], "moved, not removed"
    outputs["specialist_backend_0"].changed_files.remove("app/items.py")
    (tmp_path / "app" / "items.py").unlink()
    (tmp_path / "app" / "routes.py").write_text("import cache\n\ndef index():\n    return cache.load_items()\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == [], "the file never names the module it was removed from"
    (tmp_path / "app" / "routes.py").write_text("from app import store\n\ndef load_items():\n    return store.fetch_items()\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == [], "it defines the name itself"


def test_a_dotted_directory_keeps_its_dot(tmp_path):
    (tmp_path / ".lib").mkdir()
    (tmp_path / ".lib" / "store.py").write_text("def load_items():\n    return []\n")
    (tmp_path / ".lib" / "routes.py").write_text("x = 1\n")
    for args in (("init", "-q"), ("add", "-A"), ("-c", "user.email=h@example.com", "-c", "user.name=h", "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    (tmp_path / ".lib" / "store.py").write_text("def fetch_items():\n    return []\n")
    (tmp_path / ".lib" / "routes.py").write_text("from store import load_items\n\ndef index():\n    return load_items()\n")
    outputs = {"specialist_backend_0": SimpleNamespace(changed_files=["./.lib/store.py"]),
               "specialist_ui_ux_1": SimpleNamespace(changed_files=[".lib/routes.py"])}

    with mock.patch.dict(os.environ, ON):
        [defect] = interface_clashes.defects(tmp_path, outputs, interface_clashes.role_of)

    assert "`.lib/store.py`" in defect.description and defect.affected_files == [".lib/routes.py", ".lib/store.py"]


def test_a_moved_name_still_imported_from_its_old_file_is_a_clash_and_a_name_in_a_comment_is_not(tmp_path):
    outputs = _batch(tmp_path)
    (tmp_path / "app" / "items.py").write_text("def load_items():\n    return []\n")
    outputs["specialist_backend_0"].changed_files.append("app/items.py")
    (tmp_path / "app" / "routes.py").write_text("from app.store import load_items\n\ndef index():\n    return load_items()\n")
    with mock.patch.dict(os.environ, ON):
        assert [c["name"] for c in interface_clashes.clashes(tmp_path, outputs)] == ["load_items"], "the old import breaks"
    outputs["specialist_backend_0"].changed_files.remove("app/items.py")
    (tmp_path / "app" / "items.py").unlink()
    (tmp_path / "app" / "routes.py").write_text("from app import store\n# load_items used to live here\nX = 'load_items'\n")
    with mock.patch.dict(os.environ, ON):
        assert interface_clashes.clashes(tmp_path, outputs) == []


def test_whether_a_clash_still_stands_is_read_from_the_using_file(tmp_path):
    """Closed on any named test and held open on none, a clash was never re-checked."""
    outputs = _batch(tmp_path)
    with mock.patch.dict(os.environ, ON):
        description = interface_clashes.defects(tmp_path, outputs, interface_clashes.role_of)[0].description
    assert interface_clashes.still_clashing(tmp_path, description) is True
    (tmp_path / "app" / "routes.py").write_text("from app.store import fetch_items\n\ndef index():\n    return fetch_items()\n")
    assert interface_clashes.still_clashing(tmp_path, description) is False
    assert interface_clashes.still_clashing(tmp_path, "[AC-1] sign up fails") is None


@pytest.mark.parametrize(("routes", "status"), [
    ("from app.store import load_items\n\ndef index():\n    return load_items()\n", "open"),
    ("from app.store import fetch_items\n\ndef index():\n    return fetch_items()\n", "fixed"),
], ids=["still clashing", "settled"])
def test_a_fix_settles_a_clash_only_when_the_using_file_no_longer_imports_the_removed_name(tmp_path, routes, status):
    """Closed on any named test and held open on none, a clash was never re-checked."""
    import the_fix_stage

    outputs = _batch(tmp_path)
    with mock.patch.dict(os.environ, ON):
        [clash] = interface_clashes.defects(tmp_path, outputs, interface_clashes.role_of)
    (tmp_path / "app" / "routes.py").write_text(routes)

    raised = the_fix_stage.a_defect(clash.description, source="interface clash", owner="ui_ux",
                                    affected_files=clash.affected_files)

    update, _ = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, raised),
                                  answer=SpecialistOutput(changed_files=["app/routes.py"], tests=["tests/test_routes.py"]))

    assert update["remediation"].defects[0].status == status
