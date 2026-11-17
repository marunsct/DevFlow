"""A builder's report names every interface it added or removed, read by the harness (plan PH.3).

Behind `INTERFACE_CHANGES_NAMED`, off until measured.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from app.agents import interface_changes
from app.agents.specialists import SpecialistOutput


def _repo(root: Path) -> None:
    (root / "app").mkdir()
    (root / "app" / "store.py").write_text("def save(note):\n    pass\n\ndef load(id):\n    pass\n")
    (root / "app" / "page.js").write_text("export function render() {}\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "base"], check=True)
    (root / "app" / "store.py").write_text("def save(note):\n    pass\n\ndef fetch(id):\n    pass\n")
    (root / "app" / "page.js").write_text("export function render() {}\nexport const mount = () => {}\n")


def test_the_definitions_gained_and_lost_in_each_language_are_read(tmp_path):
    _repo(tmp_path)

    lines = interface_changes.changes(tmp_path, ["app/store.py", "app/page.js"])

    assert lines == ["Interface of `app/store.py`: added `fetch`; removed `load`.",
                     "Interface of `app/page.js`: added `mount`."]


def test_on_a_change_its_decisions_do_not_name_is_added_and_one_they_do_is_not(tmp_path):
    _repo(tmp_path)
    output = SpecialistOutput(changed_files=["app/store.py", "app/page.js"], decisions=["Added `mount` to the page."])

    with mock.patch.dict(os.environ, {"INTERFACE_CHANGES_NAMED": "on"}):
        got = interface_changes.with_them(output, tmp_path)
    with mock.patch.dict(os.environ, {"INTERFACE_CHANGES_NAMED": "off"}):
        off = interface_changes.with_them(output, tmp_path)

    assert got.decisions == ["Added `mount` to the page.", "Interface of `app/store.py`: added `fetch`; removed `load`."]
    assert off is output


@pytest.mark.parametrize("parallel", [False, True], ids=["linear", "parallel"])
def test_both_ways_a_builder_s_answer_is_kept_carry_it(tmp_path, monkeypatch, parallel):
    from workflow_node_stubs import run_a_builder

    read = []

    def with_them(output, root):
        read.append((output.changed_files, root))
        return output.model_copy(update={"decisions": ["Interface of `app/shared.js`: added `share`."]})

    monkeypatch.setattr(interface_changes, "with_them", with_them)

    seen = run_a_builder(monkeypatch, tmp_path, parallel=parallel)

    assert read == [(["app/shared.js"], str(tmp_path))]
    kept = seen.update["specialist_outputs"]["specialist_ui_ux_1"]
    assert kept.decisions == ["Interface of `app/shared.js`: added `share`."]
