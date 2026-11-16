"""A commit or a revert that did not happen is reported, not taken for done (LR.51).

Found in the launch review: a commit that failed returned the old HEAD as if the work were in it, so a later reset to
that commit discarded the work; and a revert whose clean-up failed was reported as a revert.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app import ci


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key, value in (("user.name", "t"), ("user.email", "t@t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", key, value], check=True)
    (tmp_path / "a.txt").write_text("one\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "first"], check=True)
    return tmp_path


def test_a_commit_that_could_not_happen_answers_nothing_to_go_back_to(tmp_path):
    root = _repo(tmp_path)
    (root / "a.txt").write_text("two\n")
    (root / ".git" / "index.lock").write_text("")
    assert ci.commit(root, "Fix: something") == ""
    (root / ".git" / "index.lock").unlink()
    assert ci.commit(root, "Fix: something") == ci.head(root) != ""


def test_a_commit_with_nothing_new_still_names_head(tmp_path):
    root = _repo(tmp_path)
    assert ci.commit(root, "nothing") == ci.head(root)


def test_a_revert_leaves_the_tree_as_the_commit_had_it(tmp_path):
    root = _repo(tmp_path)
    base = ci.head(root)
    (root / "a.txt").write_text("broken\n")
    (root / "new.txt").write_text("added by a fix\n")
    assert ci.revert_to(root, base) is True
    assert (root / "a.txt").read_text() == "one\n" and not (root / "new.txt").exists()
