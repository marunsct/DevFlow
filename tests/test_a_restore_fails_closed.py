"""Putting files back from a commit is all or nothing, and an unreadable commit deletes nothing (LR.51).

Found in the launch review: `restore_paths` read "git could not show this file at that commit" as "the commit did
not have it" and deleted the file, so a commit id git could not read (a typo, a pruned object, a lock) deleted every
file it was asked to restore and still answered done. A checkout that failed half way left the files it had already
put back changed, and the caller saw only False.
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
    (tmp_path / "b.txt").write_text("one\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "first"], check=True)
    return tmp_path


def test_a_commit_git_cannot_read_deletes_nothing_and_says_so(tmp_path):
    root = _repo(tmp_path)
    (root / "a.txt").write_text("two\n")
    assert ci.restore_paths(root, "0" * 40, ["a.txt", "b.txt"]) is False
    assert (root / "a.txt").read_text() == "two\n"
    assert (root / "b.txt").read_text() == "one\n"


def test_a_file_the_commit_did_not_have_is_still_removed(tmp_path):
    root = _repo(tmp_path)
    base = ci.head(root)
    (root / "new.txt").write_text("made later\n")
    (root / "a.txt").write_text("two\n")
    assert ci.restore_paths(root, base, ["a.txt", "new.txt"]) is True
    assert (root / "a.txt").read_text() == "one\n"
    assert not (root / "new.txt").exists()


def test_a_checkout_that_fails_half_way_leaves_every_file_as_it_was(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = ci.head(root)
    (root / "a.txt").write_text("two\n")
    (root / "b.txt").write_text("two\n")
    (root / "new.txt").write_text("made later\n")
    real = ci._git

    def failing_on_b(where, *args):
        if args[:1] == ("checkout",) and args[-1] == "b.txt":
            return subprocess.CompletedProcess(args, 1, "", "error: unable to write")
        return real(where, *args)

    monkeypatch.setattr(ci, "_git", failing_on_b)
    assert ci.restore_paths(root, base, ["a.txt", "new.txt", "b.txt"]) is False
    assert (root / "a.txt").read_text() == "two\n"
    assert (root / "b.txt").read_text() == "two\n"
    assert (root / "new.txt").read_text() == "made later\n"
