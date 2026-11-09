"""A commit that changes only the harness's records leaves the product's fingerprint as it was.

Measured on one run: the harness committed its decision log between two measurements of an unchanged product, the
fingerprint began with the commit's id, and the unit tests - five minutes each on a test that never settled - ran
again as if the product had changed. The fingerprint is of the product's files, not of the commit that holds them.
"""
from __future__ import annotations

import subprocess

from app.acceptance.unstable import fingerprint


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.ts").write_text("export const a = 1;\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "decision_log.md").write_text("# Decisions\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "first")
    return tmp_path


def test_a_commit_of_the_records_alone_keeps_it(tmp_path):
    root = _repo(tmp_path)
    before = fingerprint(root)
    (root / "docs" / "decision_log.md").write_text("# Decisions\n- DR-1\n")
    _git(root, "commit", "-qam", "the harness's record")

    assert fingerprint(root) == before


def test_a_commit_of_the_product_changes_it(tmp_path):
    root = _repo(tmp_path)
    before = fingerprint(root)
    (root / "app" / "main.ts").write_text("export const a = 2;\n")
    _git(root, "commit", "-qam", "a fix")

    assert fingerprint(root) != before
