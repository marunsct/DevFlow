"""The product's fingerprint changes when an untracked file's content changes, not only when its name does.

A measurement is reused while the fingerprint is the one it was taken on (`MEASURE_ONCE`); a new file changed again
before anything committed it kept the same list of untracked names and read as unchanged.
"""
from __future__ import annotations

import subprocess

from app.acceptance.unstable import fingerprint


def test_an_untracked_file_s_content_is_part_of_the_fingerprint(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kept.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    (tmp_path / "new.ts").write_text("export const a = 1;\n")
    first = fingerprint(tmp_path)

    (tmp_path / "new.ts").write_text("export const a = 2;\n")

    assert fingerprint(tmp_path) != first
