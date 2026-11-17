"""A fix that edits a manifest is blamed for a failing install only when the install worked before it.

Measured on a compiled stack whose install builds the code: with the build already failing, every fix that touched the
manifest was reverted as "it broke the install", eight in one run, and each fixer's work was lost.
"""
from __future__ import annotations

import subprocess

import pytest

from app import ci
from app.acceptance import suite
from app.graph import engineering
from app.stacks import contract, pack_named
from app.stacks.contract import INSTALL_FAILED

NOTE = f"`pip install -r requirements.txt` {INSTALL_FAILED}; it ended: error: could not compile"


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _a_project_whose_manifest_changed_at_the_base(root, *, installed_at_the_base):
    contract.write(root, pack_named("python-http-api"), "tasks", "Tasks")
    manifest = root / "tasks" / "requirements.txt"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("flask\n")
    contract.installed(root)
    manifest.write_text("flask\nhttpx\n")
    if installed_at_the_base:
        contract.installed(root)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    manifest.write_text("flask\nhttpx\nrequests\n")  # the fix
    return base


@pytest.mark.parametrize("installed_at_the_base, reverted", [(False, False), (True, True)],
                         ids=["already-failing", "worked-before"])
def test_the_install_is_the_fix_s_only_when_it_worked_before(tmp_path, monkeypatch, installed_at_the_base, reverted):
    base = _a_project_whose_manifest_changed_at_the_base(tmp_path, installed_at_the_base=installed_at_the_base)
    nothing_ran = ci.Snapshot(label="s", unit={"u1": "failed"}, unit_ran=True)
    monkeypatch.setattr(ci, "load", lambda root, which: nothing_ran)
    monkeypatch.setattr(ci, "take", lambda root, label: nothing_ran)  # the project's own tests are the edge
    monkeypatch.setattr(suite, "last_result", lambda root: {"repairs": [NOTE]})
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_0", "a dependency")

    assert bool(broke) is reverted, broke
    assert ("requests" in (tmp_path / "tasks" / "requirements.txt").read_text()) is not reverted
