"""A defect is closed at dispatch from a stored measurement only while the product is as the suite measured it.

Found in a code review of the defect-fix loop: `ci.revert_to` puts the tree back as it was before a fix, but the
suite's saved result (`acceptance-result.json`) is git-ignored and survives the revert. A reverted fix's green
measurement then closed another defect "without a fixer", and the next round raised it again. The dispatch now
reads a stored result only while `unstable.unchanged_since_the_suite_measured`; otherwise the defect's own tests are
measured again as the product is.

For that check not to refuse every closure after a kept fix, the product's fingerprint is now of its files as they
are on disk: a fix measured and then committed is the same product, before and after the commit.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from app.acceptance import unstable
from app.graph import acceptance_nodes, workflow
from app.sprint import Defect, RemediationCycle


def _cycle() -> RemediationCycle:
    return RemediationCycle(sprint_goal="Sprint 1", defects=[Defect(
        description=acceptance_nodes.THE_PRODUCT_DOES_NOT_START, severity="blocking", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner="backend",
    )])


def _the_suite_last_measured(monkeypatch, tmp_path, measured: str, now: str, probed: list[str]):
    """A locked suite whose saved run reached the product, taken on the product `measured`; the product is `now`."""
    saved = {"ran": True, "passed": 5, "failed": 0, "problem": "", "fingerprint": measured, "command": "suite"}
    monkeypatch.setattr("app.acceptance.suite.is_locked", lambda root: True)
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: saved)
    monkeypatch.setattr("app.acceptance.unstable.fingerprint", lambda root: now)
    monkeypatch.setattr("app.graph.engineering.no_longer_underlined", lambda root, description: "")
    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", lambda root, defect: probed.append("probe") and None)
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 1}


def test_a_measurement_of_another_product_closes_nothing_and_the_defect_is_measured_again(tmp_path, monkeypatch):
    probed: list[str] = []
    state = _the_suite_last_measured(monkeypatch, tmp_path, measured="the reverted fix", now="as reverted",
                                     probed=probed)

    assert workflow._closed_if_an_earlier_fix_resolved_it(state, _cycle(), 0) is None
    assert probed == ["probe"]


def test_a_measurement_of_this_product_still_closes_it(tmp_path, monkeypatch):
    probed: list[str] = []
    state = _the_suite_last_measured(monkeypatch, tmp_path, measured="same", now="same", probed=probed)

    closed = workflow._closed_if_an_earlier_fix_resolved_it(state, _cycle(), 0)

    assert closed is not None and closed["remediation"].defects[0].status != "open"
    assert probed == []


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def test_a_commit_of_what_is_on_disk_leaves_the_fingerprint_as_it_was(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.ts").write_text("export const a = 1;\n")
    (tmp_path / "app" / "old.ts").write_text("export const b = 1;\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "first")
    # A fix: one file changed, one removed, one added - measured before anything commits it.
    (tmp_path / "app" / "main.ts").write_text("export const a = 2;\n")
    (tmp_path / "app" / "old.ts").unlink()
    (tmp_path / "app" / "new.ts").write_text("export const c = 1;\n")
    measured = unstable.fingerprint(tmp_path)

    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the fix")

    assert unstable.fingerprint(tmp_path) == measured
    (tmp_path / "app" / "main.ts").write_text("export const a = 3;\n")
    assert unstable.fingerprint(tmp_path) != measured
